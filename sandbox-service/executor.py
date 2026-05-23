"""Command execution and file transfer via shared volumes.

execute() runs commands via docker exec. Files are transferred through the
shared volume (not docker cp) by exec'ing shell commands that read/write
to /workspace.

After each exec, the sandbox-service calls the platform API to update
last_exec_at for the session. This enables the cleanup job to detect
inactive sandboxes accurately across service restarts.
"""

import base64
import logging
import os
from typing import Any

import httpx
from docker.errors import APIError, NotFound

from manager import get_docker_client

logger = logging.getLogger(__name__)

MAX_OUTPUT_BYTES = 1_048_576  # 1MB output cap

PLATFORM_URL = os.environ.get("PLATFORM_URL", "http://aegra:2026")
SANDBOX_API_KEY = os.environ.get("SANDBOX_API_KEY", "")


def _report_exec(session_id: str, container_id: str) -> None:
    """Report exec activity to the platform API. Best-effort, never raises."""
    try:
        with httpx.Client() as client:
            client.post(
                f"{PLATFORM_URL}/internal/sessions/{session_id}/last-exec",
                json={"container_id": container_id},
                headers={"Authorization": f"Bearer {SANDBOX_API_KEY}"} if SANDBOX_API_KEY else {},
                timeout=5.0,
            )
    except Exception:
        logger.debug("Failed to report exec for session %s", session_id, exc_info=True)


def _get_session_id_from_container(container) -> str:
    """Extract session_id from container labels."""
    labels = container.labels or {}
    return labels.get("platform.session_id", "")


def _ensure_container_running(container_id: str) -> Any:
    """Get the container and auto-start it if it is not running.

    If the container is already running, returns immediately.
    If stopped, calls start_sandbox() (which handles network recovery)
    and verifies the container reached running status.

    Raises:
        NotFound: If the container does not exist.
        RuntimeError: If the container exists but could not be started.
    """
    from manager import start_sandbox

    client = get_docker_client()
    container = client.containers.get(container_id)
    container.reload()
    if container.status == "running":
        return container

    start_sandbox(container_id)
    container.reload()
    if container.status != "running":
        raise RuntimeError(
            f"Container {container_id[:12]} did not start (status: {container.status})"
        )
    return container


def exec_command(
    container_id: str,
    command: str,
    timeout: int | None = None,
) -> dict[str, Any]:
    """Execute a command in the container via docker exec.

    If the container is stopped, it is auto-started before the command runs.

    Args:
        container_id: Full container ID.
        command: Shell command string.
        timeout: Seconds to wait. None = no timeout (container default).

    Returns:
        {"output": str, "exit_code": int, "truncated": bool}
    """
    container = _ensure_container_running(container_id)

    # Report activity to platform API (best-effort) — before the potentially
    # long exec so the cleanup job sees fresh activity.
    session_id = _get_session_id_from_container(container)
    if session_id:
        _report_exec(session_id, container_id)

    exec_kwargs: dict[str, Any] = {
        "cmd": ["sh", "-c", command],
        "stdout": True,
        "stderr": True,
        "demux": False,  # Combine stdout+stderr
        "workdir": "/workspace",
    }

    try:
        exec_result = container.exec_run(**exec_kwargs)
    except APIError as exc:
        raise RuntimeError(f"Docker exec API error: {exc}") from exc

    raw_output = exec_result.output or b""
    if isinstance(raw_output, bytes):
        output = raw_output.decode("utf-8", errors="replace")
    else:
        output = str(raw_output)
    truncated = False
    if len(output) > MAX_OUTPUT_BYTES:
        output = output[:MAX_OUTPUT_BYTES]
        truncated = True

    return {
        "output": output,
        "exit_code": exec_result.exit_code,
        "truncated": truncated,
    }


def upload_files_to_container(
    container_id: str,
    files: list[tuple[str, bytes]],
) -> list[dict[str, Any]]:
    """Upload files to the container's workspace via shared volume.

    If the container is stopped, it is auto-started before the upload runs.
    Uses exec_run with base64-encoded content to avoid shell escaping issues.
    For each file: creates parent directories, then writes content.

    Args:
        container_id: Full container ID.
        files: List of (relative_path, content_bytes) tuples.

    Returns:
        List of {"path": str, "error": str | None} dicts.
    """
    container = _ensure_container_running(container_id)

    # Report activity to platform API (best-effort)
    session_id = _get_session_id_from_container(container)
    if session_id:
        _report_exec(session_id, container_id)

    results: list[dict[str, Any]] = []
    for path, content in files:
        try:
            # Ensure parent directory exists
            parent = os.path.dirname(path)
            if parent:
                exec_result = container.exec_run(
                    cmd=["mkdir", "-p", parent],
                    workdir="/workspace",
                )
                if exec_result.exit_code != 0:
                    raw = exec_result.output
                    error_msg = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
                    results.append({"path": path, "error": f"mkdir failed: {error_msg}"})
                    continue

            # Write file content via base64 + Python (avoids shell escaping issues)
            b64_content = base64.b64encode(content).decode("ascii")
            write_script = (
                f"import base64; "
                f"open({path!r}, 'wb').write(base64.b64decode('{b64_content}'))"
            )
            exec_result = container.exec_run(
                cmd=["python3", "-c", write_script],
                workdir="/workspace",
            )
            if exec_result.exit_code != 0:
                raw = exec_result.output
                error_msg = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
                results.append({"path": path, "error": f"write failed: {error_msg}"})
            else:
                results.append({"path": path, "error": None})

        except Exception as exc:
            logger.error("Failed to upload %s to %s: %s", path, container_id[:12], exc)
            results.append({"path": path, "error": str(exc)})

    return results


def download_file_bytes(container_id: str, file_path: str) -> bytes:
    """Download a file from the container.

    If the container is stopped, it is auto-started before the download runs.

    Args:
        container_id: Full container ID.
        file_path: Absolute or relative path. Relative paths resolve under /workspace.

    Returns:
        Raw file bytes.

    Raises:
        FileNotFoundError: If the file doesn't exist.
    """
    container = _ensure_container_running(container_id)

    # Report activity to platform API (best-effort)
    session_id = _get_session_id_from_container(container)
    if session_id:
        _report_exec(session_id, container_id)

    # Absolute paths are used as-is; relative paths resolve under /workspace
    target_path = file_path if file_path.startswith("/") else f"/workspace/{file_path.lstrip('/')}"

    exec_result = container.exec_run(
        cmd=["cat", target_path],
        workdir="/workspace",
    )

    if exec_result.exit_code != 0:
        raise FileNotFoundError(f"File not found or not readable: {target_path}")

    return exec_result.output or b""
