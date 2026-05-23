"""Pydantic schemas for sandbox service request/response models."""

from pydantic import BaseModel, field_validator


class SandboxCreateRequest(BaseModel):
    session_id: str
    environment_id: str
    agent_id: str
    packages: dict[str, list[str]] = {}
    resource_limits: dict = {}
    repositories: list[dict] = []
    repo_secrets: dict[str, str] = {}
    skill_repos: list[dict] = []
    ip_subnet: str | None = None
    base_image: str | None = None


class ImageBuildRequest(BaseModel):
    environment_id: str
    packages: dict[str, list[str]] = {}
    resource_limits: dict = {}
    base_image: str | None = None
    ip_subnet: str | None = None


class SandboxCreateResponse(BaseModel):
    container_id: str
    status: str
    ip_subnet: str | None = None


class ExecRequest(BaseModel):
    command: str
    timeout: int | None = None


class ExecResponse(BaseModel):
    output: str
    exit_code: int
    truncated: bool = False


class FileItem(BaseModel):
    path: str
    content: str  # base64-encoded bytes

    @field_validator("path")
    @classmethod
    def validate_path(cls, v: str) -> str:
        if not v:
            raise ValueError("Path must not be empty")
        if ".." in v:
            raise ValueError("Path must not contain '..'")
        return v


class FileUploadRequest(BaseModel):
    files: list[FileItem]


class FileUploadResponseItem(BaseModel):
    path: str
    error: str | None = None


class SandboxStatusResponse(BaseModel):
    container_id: str
    status: str
    last_exec_at: str | None = None
