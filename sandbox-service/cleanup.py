"""Periodic cleanup — zombie containers, inactive sandboxes, orphaned volumes, networks, images.

Runs every 5 minutes in a background asyncio task.

Zombie containers: Containers with platform.managed=true that have no matching
active session. The cleanup calls POST /internal/sessions/{id}/cleanup on the
platform to handle DB state.

Inactivity: Queries the platform's GET /internal/sessions/stale endpoint to
find sessions with no exec activity for 15+ minutes. Stops (not destroys)
those containers.

Orphaned networks: Networks with platform.managed=true that have zero attached
containers (running or stopped).

Dangling images: Dangling images with platform.managed=true label.

Old tagged images: platform.managed=true images with no containers referencing
them, created >24h ago.
"""

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone

import httpx
from docker.errors import NotFound

from manager import _DEFAULT_BASE_IMAGE, get_docker_client, get_managed_containers

logger = logging.getLogger(__name__)

CLEANUP_INTERVAL_SECONDS = 300  # 5 minutes
INACTIVITY_TIMEOUT_SECONDS = 900  # 15 minutes
IMAGE_AGE_HOURS = 24

PLATFORM_URL = os.environ.get("PLATFORM_URL", "http://aegra:2026")
SANDBOX_API_KEY = os.environ.get("SANDBOX_API_KEY", "")


def _platform_headers() -> dict[str, str]:
    if SANDBOX_API_KEY:
        return {"Authorization": f"Bearer {SANDBOX_API_KEY}"}
    return {}


async def _stop_inactive_sandboxes() -> None:
    """Stop containers for sessions that have been inactive for 15+ minutes."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{PLATFORM_URL}/internal/sessions/stale",
                params={"idle_seconds": INACTIVITY_TIMEOUT_SECONDS},
                headers=_platform_headers(),
                timeout=10.0,
            )
            resp.raise_for_status()
            stale_sessions = resp.json()
    except Exception as exc:
        logger.warning("Failed to query stale sessions: %s", exc)
        return

    docker_client = get_docker_client()
    for entry in stale_sessions:
        container_id = entry["sandbox_container_id"]
        try:
            container = docker_client.containers.get(container_id)
            if container.status == "running":
                container.stop(timeout=10)
                logger.info(
                    "Stopped inactive sandbox %s (session %s)",
                    container_id[:12],
                    entry["session_id"],
                )
        except NotFound:
            logger.debug("Container %s already removed", container_id[:12])
        except Exception as exc:
            logger.warning(
                "Failed to stop inactive sandbox %s: %s", container_id[:12], exc
            )


async def _notify_platform_cleanup(session_id: str) -> None:
    """Tell the platform to clean up a session whose sandbox was destroyed."""
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{PLATFORM_URL}/internal/sessions/{session_id}/cleanup",
                headers=_platform_headers(),
                timeout=10.0,
            )
    except Exception as exc:
        logger.warning(
            "Failed to notify platform about cleanup for session %s: %s",
            session_id,
            exc,
        )


async def _cleanup_zombie_containers() -> None:
    """Remove containers with platform.managed=true that have no matching session."""
    docker_client = get_docker_client()

    for container in get_managed_containers(docker_client):
        labels = container.labels or {}
        session_id = labels.get("platform.session_id", "")

        if not session_id:
            logger.warning(
                "Found managed container %s with no session_id label — removing",
                container.short_id,
            )
            try:
                container.remove(force=True)
            except Exception as exc:
                logger.warning(
                    "Failed to remove unlabeled container %s: %s",
                    container.short_id,
                    exc,
                )
            continue

        try:
            async with httpx.AsyncClient() as http_client:
                resp = await http_client.get(
                    f"{PLATFORM_URL}/v1/sessions/{session_id}",
                    headers=_platform_headers(),
                    timeout=10.0,
                )
                if resp.status_code == 404:
                    logger.info(
                        "Session %s not found — destroying orphaned container %s",
                        session_id,
                        container.short_id,
                    )
                    try:
                        container.remove(force=True)
                    except Exception as exc:
                        logger.warning(
                            "Failed to remove orphaned container %s: %s",
                            container.short_id,
                            exc,
                        )
                    await _notify_platform_cleanup(session_id)
                    continue

                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("archived_at"):
                        logger.info(
                            "Session %s is archived — destroying container %s",
                            session_id,
                            container.short_id,
                        )
                        try:
                            container.remove(force=True)
                        except Exception as exc:
                            logger.warning(
                                "Failed to remove archived container %s: %s",
                                container.short_id,
                                exc,
                            )
                        await _notify_platform_cleanup(session_id)
                        continue

        except Exception as exc:
            logger.warning(
                "Failed to check session %s for container %s: %s",
                session_id,
                container.short_id,
                exc,
            )

    # Clean up orphaned volumes
    try:
        for vol in docker_client.volumes.list(
            filters={"label": "platform.managed=true"}
        ):
            vol_session_id = vol.attrs.get("Labels", {}).get("platform.session_id", "")
            if not vol_session_id:
                continue

            containers_using = docker_client.containers.list(
                all=True,
                filters={"volume": vol.name},
            )
            if not containers_using:
                logger.info("Removing orphaned volume %s", vol.name)
                try:
                    vol.remove(force=True)
                except Exception as exc:
                    logger.warning(
                        "Failed to remove orphaned volume %s: %s", vol.name, exc
                    )

    except Exception as exc:
        logger.warning("Failed to scan for orphaned volumes: %s", exc)


async def _cleanup_orphaned_networks() -> None:
    """Remove managed networks with zero attached containers (running OR stopped).

    net.attrs['Containers'] only lists RUNNING containers. After the
    inactivity cleanup stops a container, that container disappears from
    the dict, so we must check all containers (all=True) by network name.
    """
    docker_client = get_docker_client()
    try:
        for net in docker_client.networks.list(
            filters={"label": "platform.managed=true"}
        ):
            # all=True includes stopped containers that still reference this network
            attached = docker_client.containers.list(
                all=True,
                filters={"network": net.name},
            )
            if not attached:
                logger.info("Removing orphaned network %s", net.name)
                try:
                    net.remove()
                except Exception as exc:
                    logger.warning("Failed to remove network %s: %s", net.name, exc)
    except Exception as exc:
        logger.warning("Failed to scan for orphaned networks: %s", exc)


async def _cleanup_images() -> None:
    """Prune dangling platform images and old unused tagged images."""
    docker_client = get_docker_client()

    # 1. Prune dangling images with our label
    try:
        pruned = docker_client.images.prune(
            filters={"label": ["platform.managed=true"]}
        )
        if pruned.get("ImagesDeleted"):
            logger.info(
                "Pruned %d dangling images (%s bytes freed)",
                len(pruned["ImagesDeleted"]),
                pruned.get("SpaceReclaimed", 0),
            )
    except Exception as exc:
        logger.warning("Failed to prune dangling images: %s", exc)

    # 2. Remove old unused tagged environment images
    cutoff = datetime.now(timezone.utc) - timedelta(hours=IMAGE_AGE_HOURS)
    try:
        for image in docker_client.images.list(
            filters={"label": "platform.managed=true"}
        ):
            # Skip base image
            if any(_DEFAULT_BASE_IMAGE in t for t in image.tags):
                continue

            created_str = image.attrs.get("Created", "")
            try:
                created = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
            except Exception:
                continue

            if created > cutoff:
                continue  # Too fresh

            # Check if any container references this image
            containers = docker_client.containers.list(
                all=True, filters={"ancestor": image.id}
            )
            if containers:
                continue

            try:
                docker_client.images.remove(image.id, force=False, noprune=False)
                logger.info(
                    "Removed unused environment image %s", image.tags or image.short_id
                )
            except Exception as exc:
                logger.debug("Could not remove image %s: %s", image.short_id, exc)
    except Exception as exc:
        logger.warning("Failed to clean up old environment images: %s", exc)

    # 3. Prune build cache (best-effort)
    try:
        docker_client.api.prune_builds()
    except Exception as exc:
        logger.debug("Build cache prune failed: %s", exc)


async def start_cleanup_task() -> None:
    """Background task that runs cleanup every CLEANUP_INTERVAL_SECONDS."""
    logger.info(
        "Starting cleanup task (interval=%ds, inactivity_timeout=%ds)",
        CLEANUP_INTERVAL_SECONDS,
        INACTIVITY_TIMEOUT_SECONDS,
    )

    while True:
        try:
            await _stop_inactive_sandboxes()
            await _cleanup_zombie_containers()
            await _cleanup_orphaned_networks()
            await _cleanup_images()
        except Exception as exc:
            logger.error("Cleanup task error: %s", exc)

        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
