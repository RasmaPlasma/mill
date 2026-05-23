"""Sandbox service — HTTP API for Docker container lifecycle and execution.

Manages per-session Docker containers with resource limits, shared volume
file transfer, and periodic zombie cleanup.

Container labels for lifecycle management:
    platform.managed=true
    platform.session_id={session_id}
    platform.environment_id={env_id}
    platform.agent_id={agent_id}
"""

import asyncio
import base64
import logging
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from cleanup import start_cleanup_task
from executor import exec_command, download_file_bytes, upload_files_to_container
from manager import (
    build_image_for_environment,
    create_sandbox,
    destroy_sandbox,
    get_sandbox_status,
    start_sandbox,
    stop_sandbox,
)
from schemas import (
    ExecRequest,
    ExecResponse,
    FileUploadRequest,
    ImageBuildRequest,
    SandboxCreateRequest,
    SandboxCreateResponse,
    SandboxStatusResponse,
    FileUploadResponseItem,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

SANDBOX_API_KEY = os.environ.get("SANDBOX_API_KEY", "")
security = HTTPBearer()


async def verify_api_key(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> None:
    """Validate the shared API key sent by the platform."""
    if not SANDBOX_API_KEY:
        return  # No key configured — open access (dev mode)
    if credentials.credentials != SANDBOX_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start background cleanup tasks on startup."""
    task = asyncio.create_task(start_cleanup_task())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="Sandbox Service",
    description="Docker container lifecycle management for the agents platform.",
    version="0.1.0",
    lifespan=lifespan,
)


@app.post("/sandboxes", response_model=SandboxCreateResponse, status_code=201)
async def create_sandbox_endpoint(
    body: SandboxCreateRequest,
    _: None = Depends(verify_api_key),
):
    """Create a sandbox container from environment config."""
    try:
        result = create_sandbox(
            session_id=body.session_id,
            environment_id=body.environment_id,
            agent_id=body.agent_id,
            packages=body.packages,
            resource_limits=body.resource_limits,
            repositories=body.repositories,
            repo_secrets=body.repo_secrets,
            skill_repos=body.skill_repos,
            ip_subnet=body.ip_subnet,
            base_image=body.base_image,
        )
    except Exception as exc:
        logger.error("Failed to create sandbox: %s", exc)
        raise HTTPException(status_code=500, detail=f"Failed to create sandbox: {exc}")

    return SandboxCreateResponse(
        container_id=result["container_id"],
        status=result["status"],
        ip_subnet=result.get("ip_subnet"),
    )


@app.post("/sandboxes/{container_id}/exec", response_model=ExecResponse)
async def exec_command_endpoint(
    container_id: str,
    body: ExecRequest,
    _: None = Depends(verify_api_key),
):
    """Execute a command in a sandbox container."""
    try:
        result = await asyncio.to_thread(
            exec_command, container_id, body.command, body.timeout
        )
    except Exception as exc:
        logger.error("Exec failed for %s: %s", container_id, exc)
        raise HTTPException(status_code=500, detail=f"Exec failed: {exc}")

    return ExecResponse(
        output=result["output"],
        exit_code=result["exit_code"],
        truncated=result.get("truncated", False),
    )


@app.post(
    "/sandboxes/{container_id}/files", response_model=list[FileUploadResponseItem]
)
async def upload_files_endpoint(
    container_id: str,
    body: FileUploadRequest,
    _: None = Depends(verify_api_key),
):
    """Upload files to a sandbox container's workspace via shared volume."""
    try:
        # f.content is base64-encoded string from JSON — decode to bytes
        decoded_files = []
        for f in body.files:
            try:
                file_bytes = base64.b64decode(f.content)
            except Exception:
                file_bytes = f.content.encode("utf-8")
            decoded_files.append((f.path, file_bytes))

        results = await asyncio.to_thread(
            upload_files_to_container,
            container_id,
            decoded_files,
        )
    except Exception as exc:
        logger.error("Upload failed for %s: %s", container_id, exc)
        raise HTTPException(status_code=500, detail=f"Upload failed: {exc}")

    return [
        FileUploadResponseItem(path=r["path"], error=r.get("error")) for r in results
    ]


@app.get("/sandboxes/{container_id}/files/{file_path:path}")
async def download_file_endpoint(
    container_id: str,
    file_path: str,
    _: None = Depends(verify_api_key),
):
    """Download a file from a sandbox container's workspace."""
    from fastapi.responses import Response

    try:
        content = await asyncio.to_thread(download_file_bytes, container_id, file_path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"File not found: {file_path}")
    except Exception as exc:
        logger.error("Download failed for %s/%s: %s", container_id, file_path, exc)
        raise HTTPException(status_code=500, detail=f"Download failed: {exc}")

    return Response(content=content, media_type="application/octet-stream")


@app.delete("/sandboxes/{container_id}", status_code=204)
async def destroy_sandbox_endpoint(
    container_id: str,
    _: None = Depends(verify_api_key),
):
    """Stop and remove a sandbox container and its per-session volume."""
    try:
        await asyncio.to_thread(destroy_sandbox, container_id)
    except Exception as exc:
        logger.error("Destroy failed for %s: %s", container_id, exc)
        raise HTTPException(status_code=500, detail=f"Destroy failed: {exc}")


@app.post("/sandboxes/{container_id}/stop", status_code=204)
async def stop_sandbox_endpoint(
    container_id: str,
    _: None = Depends(verify_api_key),
):
    """Stop a running sandbox container (preserves volume)."""
    try:
        await asyncio.to_thread(stop_sandbox, container_id)
    except Exception as exc:
        logger.error("Stop failed for %s: %s", container_id, exc)
        raise HTTPException(status_code=500, detail=f"Stop failed: {exc}")


@app.post("/sandboxes/{container_id}/start", status_code=204)
async def start_sandbox_endpoint(
    container_id: str,
    _: None = Depends(verify_api_key),
):
    """Start a stopped sandbox container."""
    try:
        await asyncio.to_thread(start_sandbox, container_id)
    except Exception as exc:
        logger.error("Start failed for %s: %s", container_id, exc)
        raise HTTPException(status_code=500, detail=f"Start failed: {exc}")


@app.get("/sandboxes/{container_id}/status", response_model=SandboxStatusResponse)
async def get_sandbox_status_endpoint(
    container_id: str,
    _: None = Depends(verify_api_key),
):
    """Get sandbox container status."""
    try:
        info = await asyncio.to_thread(get_sandbox_status, container_id)
    except Exception as exc:
        logger.error("Status check failed for %s: %s", container_id, exc)
        raise HTTPException(status_code=500, detail=f"Status check failed: {exc}")

    return SandboxStatusResponse(
        container_id=info["container_id"],
        status=info["status"],
        last_exec_at=info.get("last_exec_at"),
    )


@app.post("/images/build")
async def build_image_endpoint(
    body: ImageBuildRequest,
    _: None = Depends(verify_api_key),
):
    """Pre-build a Docker image for an environment.

    Returns the image tag that was built (or reused from cache).
    """
    try:
        image_tag = await asyncio.to_thread(
            build_image_for_environment,
            body.environment_id,
            body.packages,
            body.base_image,
        )
    except Exception as exc:
        logger.error("Failed to build image for env %s: %s", body.environment_id, exc)
        raise HTTPException(status_code=500, detail=f"Image build failed: {exc}")

    return {"image_tag": image_tag, "environment_id": body.environment_id}


@app.get("/health")
async def health():
    return {"status": "ok"}
