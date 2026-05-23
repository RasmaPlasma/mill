"""Container lifecycle management — create, start, stop, destroy.

All Docker operations go through the socket proxy at DOCKER_HOST.
Per-session volumes: sandbox-workspace-{session_id}.
Per-environment networks: sandbox-env-{environment_id} with explicit /28 subnets.
"""

import hashlib
import io
import ipaddress
import json
import logging
import os
import shlex

import docker
from docker.errors import APIError, ImageNotFound, NotFound

# executor is imported lazily inside _run_init_script to avoid circular imports
# (executor imports get_docker_client from this module).

logger = logging.getLogger(__name__)

DOCKER_HOST = os.environ.get("DOCKER_HOST", "tcp://docker-proxy:2375")
DOCKER_RUNTIME = os.environ.get("DOCKER_RUNTIME", "")
SANDBOX_DNS_SERVERS = os.environ.get("SANDBOX_DNS_SERVERS", "")

_DEFAULT_BASE_IMAGE = "deepagents/sandbox-base:latest"
_SUBNET_POOL = ipaddress.IPv4Network("10.224.0.0/12")
_SUBNET_PREFIX_LEN = 28


def get_docker_client() -> docker.DockerClient:
    """Create a Docker client connected to the socket proxy."""
    return docker.DockerClient(base_url=DOCKER_HOST)


def _compute_build_key(
    client: docker.DockerClient, packages: dict, base_image: str
) -> str:
    base_id = ""
    try:
        img = client.images.get(base_image)
        base_id = img.id
    except ImageNotFound:
        pass
    canonical = json.dumps(
        {"base": base_image, "base_id": base_id, "packages": packages},
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def _build_base_image(client: docker.DockerClient) -> str:
    """Ensure the shared sandbox base image exists locally."""
    try:
        client.images.get(_DEFAULT_BASE_IMAGE)
        logger.info("Reusing cached base image %s", _DEFAULT_BASE_IMAGE)
        return _DEFAULT_BASE_IMAGE
    except ImageNotFound:
        pass

    dockerfile_path = os.path.join(os.path.dirname(__file__), "Dockerfile.base")
    with open(dockerfile_path, "r") as f:
        dockerfile = f.read()
    logger.info("Building base image %s", _DEFAULT_BASE_IMAGE)
    image, _ = client.images.build(
        fileobj=io.BytesIO(dockerfile.encode()),
        tag=_DEFAULT_BASE_IMAGE,
        rm=True,
        forcerm=True,
        labels={"platform.managed": "true", "platform.role": "base"},
    )
    logger.info("Built base image %s (%s)", _DEFAULT_BASE_IMAGE, image.short_id)
    return _DEFAULT_BASE_IMAGE


def _build_image(
    client: docker.DockerClient,
    environment_id: str,
    packages: dict[str, list[str]],
    base_image: str | None,
) -> str:
    """Build or return cached per-environment image.

    Uses content-addressable tags so package changes trigger rebuilds.
    """
    resolved_base = base_image or _DEFAULT_BASE_IMAGE
    # Ensure base exists
    if resolved_base == _DEFAULT_BASE_IMAGE:
        _build_base_image(client)

    build_key = _compute_build_key(client, packages, resolved_base)
    tag = f"sandbox-env-{environment_id}:{build_key}"

    try:
        client.images.get(tag)
        logger.info("Reusing cached image %s", tag)
        return tag
    except ImageNotFound:
        pass

    pip_packages = " ".join(packages.get("pip", []))
    npm_packages = " ".join(packages.get("npm", []))
    apt_packages = " ".join(packages.get("apt", []))

    apt_deps = []
    if npm_packages:
        apt_deps.extend(["nodejs", "npm"])
    apt_deps.extend(apt_packages.split() if apt_packages else [])

    dockerfile_lines = [f"FROM {resolved_base}"]

    if apt_deps:
        dockerfile_lines.append(
            "RUN apt-get update && apt-get install -y --no-install-recommends "
            + " ".join(apt_deps)
            + " && rm -rf /var/lib/apt/lists/*"
        )

    if pip_packages:
        dockerfile_lines.append(f"RUN pip install --break-system-packages --no-cache-dir {pip_packages}")
    if npm_packages:
        dockerfile_lines.append(f"RUN npm install -g {npm_packages}")

    dockerfile_lines.extend(
        [
            "WORKDIR /workspace",
            'CMD ["tail", "-f", "/dev/null"]',
        ]
    )

    dockerfile_content = "\n".join(dockerfile_lines)
    logger.info("Building image %s with Dockerfile:\n%s", tag, dockerfile_content)

    image, _ = client.images.build(
        fileobj=io.BytesIO(dockerfile_content.encode()),
        tag=tag,
        rm=True,
        forcerm=True,
        labels={
            "platform.managed": "true",
            "platform.environment_id": environment_id,
            "platform.build_key": build_key,
        },
    )
    logger.info("Built image %s (%s)", tag, image.short_id)
    return tag


def _allocate_subnet(client: docker.DockerClient) -> str:
    """Allocate the next free /28 from 10.224.0.0/12.

    Scans existing Docker networks to avoid overlap.
    """
    used_subnets: set[str] = set()
    for net in client.networks.list():
        ipam = net.attrs.get("IPAM") or {}
        for cfg in (ipam.get("Config") or []):
            subnet = cfg.get("Subnet")
            if subnet:
                used_subnets.add(subnet)

    # Enumerate /28 subnets inside 10.224.0.0/12
    # /12 = 2^20 addresses; /28 = 16 addresses => 65536 subnets
    for subnet in _SUBNET_POOL.subnets(new_prefix=_SUBNET_PREFIX_LEN):
        if str(subnet) not in used_subnets:
            return str(subnet)

    raise RuntimeError("Exhausted all /28 subnets in 10.224.0.0/12")


def _ensure_network(
    client: docker.DockerClient,
    environment_id: str,
    ip_subnet: str | None,
) -> tuple[str, str]:
    """Ensure a per-environment Docker network exists.

    Returns (network_name, actual_subnet).
    If ip_subnet is provided, it is reused; otherwise one is allocated.
    """
    network_name = f"sandbox-env-{environment_id}"
    networks = client.networks.list(names=[network_name])
    if networks:
        # Already exists — inspect its subnet
        net = networks[0]
        ipam = net.attrs.get("IPAM") or {}
        cfgs = ipam.get("Config") or []
        actual = cfgs[0].get("Subnet") if cfgs else ip_subnet
        return network_name, actual or ip_subnet

    if not ip_subnet:
        ip_subnet = _allocate_subnet(client)

    gateway = str(ipaddress.IPv4Network(ip_subnet)[1])
    client.networks.create(
        network_name,
        driver="bridge",
        ipam={"Config": [{"Subnet": ip_subnet, "Gateway": gateway}]},
        labels={
            "platform.managed": "true",
            "platform.environment_id": environment_id,
        },
    )
    logger.info("Created network %s (%s)", network_name, ip_subnet)
    return network_name, ip_subnet


def _create_volume(
    client: docker.DockerClient,
    session_id: str,
) -> str:
    """Create a per-session volume. Returns volume name."""
    volume_name = f"sandbox-workspace-{session_id}"
    try:
        client.volumes.get(volume_name)
        logger.info("Reusing existing volume %s", volume_name)
    except NotFound:
        client.volumes.create(
            name=volume_name,
            labels={"platform.managed": "true", "platform.session_id": session_id},
        )
        logger.info("Created volume %s", volume_name)
    return volume_name


def _run_init_script(
    container_id: str,
    repositories: list[dict] | None,
    repo_secrets: dict[str, str] | None,
    skill_repos: list[dict] | None,
) -> None:
    """Run one-time init inside the container (git clones, skill installs, etc.).

    Skips if /workspace/.sandbox-init-done exists (handles restarts).
    Credentials are passed inline and never persisted inside the container.
    Skill installs use ``npx skills add`` (headless via ``-y``) and target
    ``/workspace/.deepagents/agent/skills/`` (``HOME=/workspace``).
    Bad skill installs are logged as warnings but do not block container startup.
    """
    from executor import exec_command

    repositories = repositories or []
    repo_secrets = repo_secrets or {}
    skill_repos = skill_repos or []

    guard_check = exec_command(
        container_id,
        "test -f /workspace/.sandbox-init-done && echo 'SKIP' || echo 'RUN'",
        timeout=10,
    )
    if guard_check["output"].strip() == "SKIP":
        logger.info("Init already done for %s", container_id[:12])
        return

    lines = ["set -e"]

    # Explicit DNS config — gVisor cannot reach Docker's embedded resolver.
    if SANDBOX_DNS_SERVERS:
        dns_servers = [s.strip() for s in SANDBOX_DNS_SERVERS.split(",") if s.strip()]
        if dns_servers:
            lines.append("echo '# Generated by sandbox-service' > /etc/resolv.conf")
            for s in dns_servers:
                lines.append(f"echo 'nameserver {s}' >> /etc/resolv.conf")
    for repo in repositories:
        url = repo.get("url", "")
        branch = repo.get("branch", "main")
        depth = repo.get("depth", 1)
        path = repo.get("path", "")
        auth_secret_name = repo.get("auth_secret_name")

        if not url:
            continue

        target = f"/workspace/{path}" if path else "/workspace/repo"
        # Ensure unique target to avoid collisions
        if len(repositories) > 1 and not path:
            slug = url.rstrip("/").split("/")[-1].replace(".git", "")
            target = f"/workspace/{slug}"

        # Inject credential inline if available
        clone_url = url
        if auth_secret_name and auth_secret_name in repo_secrets:
            token = repo_secrets[auth_secret_name]
            # Replace https:// with https://<token>@
            if clone_url.startswith("https://"):
                clone_url = clone_url.replace("https://", f"https://{token}@", 1)

        depth_flag = f" --depth {depth}" if depth else ""
        lines.append(f"mkdir -p {target}")
        lines.append(
            f"git clone --branch {branch}{depth_flag} --single-branch "
            f"'{clone_url}' {target}"
        )

    # Install skills via the official skills CLI.
    # HOME=/workspace ensures global installs land in /workspace/.agents/skills/
    # (the canonical path for Deep Agents per the skills CLI).
    if skill_repos:
        for sr in skill_repos:
            repo_url = sr.get("repo", "")
            if not repo_url:
                continue
            skill_name = sr.get("skill_name", "")
            cmd = (
                f"export HOME=/workspace && "
                f"npx skills add {shlex.quote(repo_url)} -g -a deepagents -y"
            )
            if skill_name:
                cmd += f" -s {shlex.quote(skill_name)}"
            else:
                cmd += " -s '*'"
            lines.append(
                f"{cmd} || echo 'SKILL_INSTALL_FAILED: {shlex.quote(repo_url)}'"
            )

    lines.append("touch /workspace/.sandbox-init-done")
    script = "\n".join(lines)

    logger.info("Running init script for %s", container_id[:12])
    result = exec_command(container_id, script, timeout=120)
    if result["exit_code"] != 0:
        logger.warning(
            "Init script failed for %s: exit=%s output=%s",
            container_id[:12],
            result["exit_code"],
            result["output"][:500],
        )
    else:
        logger.info("Init script succeeded for %s", container_id[:12])


def build_image_for_environment(
    environment_id: str,
    packages: dict[str, list[str]] | None,
    base_image: str | None,
) -> str:
    """Build or reuse cached image for an environment. Returns the image tag."""
    client = get_docker_client()
    return _build_image(client, environment_id, packages or {}, base_image)


def create_sandbox(
    session_id: str,
    environment_id: str,
    agent_id: str,
    packages: dict[str, list[str]] | None,
    resource_limits: dict | None,
    repositories: list[dict] | None,
    repo_secrets: dict[str, str] | None,
    skill_repos: list[dict] | None,
    ip_subnet: str | None,
    base_image: str | None,
) -> dict:
    """Create a sandbox container with resource limits and labels.

    Returns {"container_id": str, "status": str, "ip_subnet": str}.
    """
    client = get_docker_client()
    packages = packages or {}
    resource_limits = resource_limits or {}
    repositories = repositories or []
    repo_secrets = repo_secrets or {}
    skill_repos = skill_repos or []

    image_tag = _build_image(client, environment_id, packages, base_image)
    network_name, actual_subnet = _ensure_network(client, environment_id, ip_subnet)
    volume_name = _create_volume(client, session_id)

    memory = resource_limits.get("memory", "1g")
    cpus = float(resource_limits.get("cpus", 1.0))
    pids_limit = int(resource_limits.get("pids_limit", 256))

    container_name = f"sandbox-{session_id}"

    run_kwargs = {
        "command": ["tail", "-f", "/dev/null"],
        "detach": True,
        "name": container_name,
        "volumes": {volume_name: {"bind": "/workspace", "mode": "rw"}},
        "working_dir": "/workspace",
        "mem_limit": memory,
        "memswap_limit": memory,
        "cpu_period": 100000,
        "cpu_quota": int(cpus * 100000),
        "pids_limit": pids_limit,
        "tmpfs": {"/tmp": "size=200m", "/var/tmp": "size=100m"},
        "cap_drop": ["ALL"],
        "security_opt": ["no-new-privileges"],
        "labels": {
            "platform.managed": "true",
            "platform.session_id": session_id,
            "platform.environment_id": environment_id,
            "platform.agent_id": agent_id,
        },
        "network": network_name,
    }

    if DOCKER_RUNTIME:
        run_kwargs["runtime"] = DOCKER_RUNTIME

    if SANDBOX_DNS_SERVERS:
        run_kwargs["dns"] = [
            s.strip() for s in SANDBOX_DNS_SERVERS.split(",") if s.strip()
        ]
    elif DOCKER_RUNTIME == "runsc":
        logger.warning(
            "DOCKER_RUNTIME=runsc but SANDBOX_DNS_SERVERS is not set. "
            "DNS resolution may fail on custom bridge networks. "
            "Set SANDBOX_DNS_SERVERS=8.8.8.8,1.1.1.1 in your environment."
        )

    container = client.containers.run(image=image_tag, **run_kwargs)

    logger.info(
        "Created sandbox %s (container=%s, image=%s, network=%s/%s, volume=%s, mem=%s, cpus=%s, runtime=%s)",
        container_name,
        container.short_id,
        image_tag,
        network_name,
        actual_subnet,
        volume_name,
        memory,
        cpus,
        DOCKER_RUNTIME or "default",
    )

    # Run init script (git clones, skill installs, etc.)
    _run_init_script(container.id, repositories, repo_secrets, skill_repos)

    return {
        "container_id": container.id,
        "status": "running",
        "ip_subnet": actual_subnet,
    }


def stop_sandbox(container_id: str) -> None:
    """Stop a running container (docker stop, not rm)."""
    client = get_docker_client()
    container = client.containers.get(container_id)
    container.stop(timeout=10)
    logger.info("Stopped sandbox %s", container_id[:12])


def start_sandbox(container_id: str) -> None:
    """Start a stopped container.

    If the container's network was removed (e.g. by the orphaned-network
    cleanup job before the container-attachment check was fixed), the first
    start() call fails with a "network not found" error.  We detect that,
    recreate the network from the container's labels, and retry once.
    """
    client = get_docker_client()
    container = client.containers.get(container_id)

    container.reload()
    if container.status == "running":
        return

    labels = container.labels or {}
    env_id = labels.get("platform.environment_id", "")

    try:
        container.start()
        logger.info("Started sandbox %s", container_id[:12])
        return
    except APIError as exc:
        msg = str(exc)
        if "network" not in msg.lower() or "not found" not in msg.lower():
            raise

        logger.warning(
            "Sandbox %s start failed because its network is missing: %s",
            container_id[:12],
            msg,
        )

        if not env_id:
            logger.error(
                "Cannot recreate network for sandbox %s — "
                "missing platform.environment_id label",
                container_id[:12],
            )
            raise

        network_name, subnet = _ensure_network(client, env_id, ip_subnet=None)
        logger.info(
            "Recreated network %s (%s) for sandbox %s",
            network_name,
            subnet,
            container_id[:12],
        )

        # Reconnect the container to the newly created network
        network = client.networks.get(network_name)
        network.connect(container_id)
        logger.info(
            "Reconnected sandbox %s to network %s",
            container_id[:12],
            network_name,
        )

        # Retry start
        container.reload()
        container.start()
        logger.info(
            "Started sandbox %s after network recovery",
            container_id[:12],
        )


def destroy_sandbox(container_id: str) -> None:
    """Remove container and its per-session volume.

    Extracts the session_id from container labels to find the volume.
    """
    client = get_docker_client()
    try:
        container = client.containers.get(container_id)
        labels = container.labels or {}
        session_id = labels.get("platform.session_id", "")

        # Remove container
        try:
            container.stop(timeout=5)
        except (NotFound, APIError):
            pass
        container.remove(force=True)
        logger.info("Destroyed sandbox container %s", container_id[:12])

        # Remove per-session volume
        if session_id:
            volume_name = f"sandbox-workspace-{session_id}"
            try:
                vol = client.volumes.get(volume_name)
                vol.remove(force=True)
                logger.info("Destroyed volume %s", volume_name)
            except NotFound:
                pass

    except NotFound:
        logger.warning("Container %s not found during destroy", container_id[:12])


def get_sandbox_status(container_id: str) -> dict:
    """Get container status and metadata."""
    client = get_docker_client()
    container = client.containers.get(container_id)
    container.reload()
    return {
        "container_id": container.id,
        "status": container.status,
    }


def get_managed_containers(client: docker.DockerClient | None = None) -> list:
    """List all containers with platform.managed=true label."""
    if client is None:
        client = get_docker_client()
    return client.containers.list(
        all=True,
        filters={"label": "platform.managed=true"},
    )
