"""DockerSandboxBackend — BaseSandbox implementation backed by sandbox-service.

Delegates all execution and file operations to the sandbox-service HTTP API.
The sandbox-service manages Docker containers; this backend is the thin
client that Deep Agents' FilesystemMiddleware calls.

Synchronous httpx.Client is used because BaseSandbox.execute() is synchronous.
The async aexecute() is provided by the parent class via asyncio.to_thread().
"""

import base64
import logging
import threading
from typing import Any

import httpx
from deepagents.backends.protocol import (
    FILE_NOT_FOUND,
    ExecuteResponse,
    FileDownloadResponse,
    FileUploadResponse,
)
from deepagents.backends.sandbox import BaseSandbox

logger = logging.getLogger(__name__)

MAX_OUTPUT_BYTES = 1_048_576


class DockerSandboxBackend(BaseSandbox):
    """Sandbox backend that delegates to the sandbox-service HTTP API.

    Args:
        container_id: Full 64-char hex container ID.
        sandbox_service_url: Base URL of the sandbox-service (e.g., http://sandbox-service:8090).
        api_key: Shared API key for sandbox-service auth. None = no auth.
    """

    def __init__(
        self,
        container_id: str,
        sandbox_service_url: str,
        api_key: str | None = None,
    ) -> None:
        self._container_id = container_id
        self._sandbox_service_url = sandbox_service_url.rstrip("/")
        headers: dict[str, str] = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self._client = httpx.Client(
            base_url=self._sandbox_service_url,
            timeout=httpx.Timeout(300.0, connect=10.0),
            headers=headers,
        )

    @property
    def id(self) -> str:
        return self._container_id

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        """Execute a shell command in the Docker container via sandbox-service.

        Calls POST /sandboxes/{id}/exec. Synchronous — required by BaseSandbox.
        The async aexecute() is inherited from BaseSandbox via asyncio.to_thread().
        """
        payload: dict[str, Any] = {"command": command}
        if timeout is not None:
            payload["timeout"] = timeout

        try:
            resp = self._client.post(
                f"/sandboxes/{self._container_id}/exec",
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            return ExecuteResponse(
                output=data["output"],
                exit_code=data["exit_code"],
                truncated=data.get("truncated", False),
            )
        except httpx.HTTPStatusError as exc:
            logger.error(
                "Sandbox exec HTTP error: %s %s",
                exc.response.status_code, exc.response.text,
            )
            return ExecuteResponse(
                output=f"Sandbox exec error ({exc.response.status_code}): {exc.response.text}",
                exit_code=1,
            )
        except httpx.RequestError as exc:
            logger.error("Sandbox exec connection error: %s", exc)
            return ExecuteResponse(
                output=f"Sandbox connection error: {exc}",
                exit_code=1,
            )

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        """Upload files to the container's workspace via sandbox-service.

        Calls POST /sandboxes/{id}/files with base64-encoded contents.
        Supports partial success — per-file error handling.
        """
        encoded_files = [
            {"path": path, "content": base64.b64encode(content).decode("ascii")}
            for path, content in files
        ]

        try:
            resp = self._client.post(
                f"/sandboxes/{self._container_id}/files",
                json={"files": encoded_files},
            )
            resp.raise_for_status()
            results = resp.json()
            return [
                FileUploadResponse(
                    path=r["path"],
                    error=r.get("error"),
                )
                for r in results
            ]
        except Exception as exc:
            logger.error("Sandbox upload error: %s", exc)
            return [
                FileUploadResponse(
                    path=path,
                    error=f"Upload failed: {exc}",
                )
                for path, _ in files
            ]

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        """Download files from the container's workspace via sandbox-service.

        Calls GET /sandboxes/{id}/files/{path} for each file.
        Supports partial success — per-file error handling.
        """
        results: list[FileDownloadResponse] = []

        for path in paths:
            try:
                resp = self._client.get(
                    f"/sandboxes/{self._container_id}/files/{path}",
                )
                if resp.status_code == 404:
                    results.append(FileDownloadResponse(
                        path=path,
                        error=FILE_NOT_FOUND,
                    ))
                else:
                    resp.raise_for_status()
                    results.append(FileDownloadResponse(
                        path=path,
                        content=resp.content,
                    ))
            except httpx.HTTPStatusError as exc:
                logger.error("Download error for %s: %s", path, exc)
                results.append(FileDownloadResponse(
                    path=path,
                    error=f"Download failed: {exc.response.status_code}",
                ))
            except Exception as exc:
                logger.error("Download error for %s: %s", path, exc)
                results.append(FileDownloadResponse(
                    path=path,
                    error=f"Download failed: {exc}",
                ))

        return results


class LazyDockerSandboxBackend(BaseSandbox):
    """Sandbox backend that creates the Docker container lazily on first tool call.

    Accepts first-tool-call latency in exchange for maximum TTFT when the
    model does not need the sandbox (no tool calls). Thread-safe — concurrent
    tool calls block on a single Lock while one thread creates the container.
    """

    def __init__(
        self,
        session_id: str,
        environment_id: str,
        agent_id: str,
        packages: dict,
        resource_limits: dict,
        repositories: list[dict],
        repo_secrets: dict[str, str],
        skill_repos: list[dict],
        ip_subnet: str | None,
        base_image: str | None,
        sandbox_service_url: str,
        api_key: str | None,
        platform_url: str,
    ) -> None:
        self._session_id = session_id
        self._environment_id = environment_id
        self._agent_id = agent_id
        self._packages = packages
        self._resource_limits = resource_limits
        self._repositories = repositories
        self._repo_secrets = repo_secrets
        self._skill_repos = skill_repos
        self._ip_subnet = ip_subnet
        self._base_image = base_image
        self._sandbox_service_url = sandbox_service_url.rstrip("/")
        self._api_key = api_key
        self._platform_url = platform_url.rstrip("/")
        self._lock = threading.Lock()
        self._backend: DockerSandboxBackend | None = None
        self._error: str | None = None

        headers: dict[str, str] = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self._client = httpx.Client(
            base_url=self._sandbox_service_url,
            timeout=httpx.Timeout(300.0, connect=10.0),
            headers=headers,
        )

    def _ensure_backend(self) -> DockerSandboxBackend | None:
        """Create the container on first call, then return the real backend.

        Returns None if creation fails permanently. Thread-safe.
        """
        with self._lock:
            if self._backend is not None:
                return self._backend
            if self._error is not None:
                return None

            try:
                resp = self._client.post(
                    "/sandboxes",
                    json={
                        "session_id": self._session_id,
                        "environment_id": self._environment_id,
                        "agent_id": self._agent_id,
                        "packages": self._packages,
                        "resource_limits": self._resource_limits,
                        "repositories": self._repositories,
                        "repo_secrets": self._repo_secrets,
                        "skill_repos": self._skill_repos,
                        "ip_subnet": self._ip_subnet,
                        "base_image": self._base_image,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                container_id = data["container_id"]

                # Notify platform so the session row gets the container_id
                try:
                    platform_headers: dict[str, str] = {}
                    if self._api_key:
                        platform_headers["Authorization"] = f"Bearer {self._api_key}"
                    platform_resp = httpx.post(
                        f"{self._platform_url}/internal/sessions/{self._session_id}/sandbox",
                        json={"container_id": container_id},
                        headers=platform_headers,
                        timeout=10.0,
                    )
                    platform_resp.raise_for_status()
                except Exception as exc:
                    logger.warning(
                        "Failed to notify platform of new container_id: %s", exc
                    )
            except Exception as exc:
                logger.error("Failed to create sandbox: %s", exc)
                self._error = f"Failed to create sandbox: {exc}"
                return None

            self._backend = DockerSandboxBackend(
                container_id=container_id,
                sandbox_service_url=self._sandbox_service_url,
                api_key=self._api_key,
            )
            return self._backend

    @property
    def id(self) -> str:
        if self._backend is not None:
            return self._backend.id
        return ""

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        backend = self._ensure_backend()
        if backend is None:
            return ExecuteResponse(
                output=f"Sandbox error: {self._error}",
                exit_code=1,
            )
        return backend.execute(command, timeout=timeout)

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        backend = self._ensure_backend()
        if backend is None:
            return [
                FileUploadResponse(
                    path=path,
                    error=f"Sandbox error: {self._error}",
                )
                for path, _ in files
            ]
        return backend.upload_files(files)

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        backend = self._ensure_backend()
        if backend is None:
            return [
                FileDownloadResponse(
                    path=path,
                    error=f"Sandbox error: {self._error}",
                )
                for path in paths
            ]
        return backend.download_files(paths)
