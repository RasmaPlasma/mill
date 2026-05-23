"""Pydantic schemas for environment CRUD operations."""

from datetime import datetime

from pydantic import BaseModel, field_validator


class NetworkingConfig(BaseModel):
    type: str = "limited"
    allowed_hosts: list[str] = []
    allow_package_managers: bool = False


class ResourceLimits(BaseModel):
    memory: str = "1g"
    cpus: float = 1.0
    pids_limit: int = 256


class PackagesConfig(BaseModel):
    pip: list[str] = []
    npm: list[str] = []
    apt: list[str] = []


class RepositoryConfig(BaseModel):
    url: str
    branch: str = "main"
    path: str = ""  # sub-directory inside /workspace
    depth: int | None = 1  # None = full clone
    auth_secret_name: str | None = None

    @field_validator("path")
    @classmethod
    def validate_path(cls, v: str) -> str:
        if ".." in v:
            raise ValueError("Path must not contain '..'")
        if v.startswith("/"):
            raise ValueError("Path must be relative (no leading /)")
        return v


class SkillRepoConfig(BaseModel):
    repo: str
    skill_name: str | None = "*"


class EnvironmentCreate(BaseModel):
    name: str
    packages: PackagesConfig = PackagesConfig()
    networking: NetworkingConfig = NetworkingConfig()
    resource_limits: ResourceLimits = ResourceLimits()
    repositories: list[RepositoryConfig] = []
    skill_repos: list[SkillRepoConfig] = []
    base_image: str | None = None


class EnvironmentUpdate(BaseModel):
    name: str | None = None
    packages: PackagesConfig | None = None
    networking: NetworkingConfig | None = None
    resource_limits: ResourceLimits | None = None
    repositories: list[RepositoryConfig] | None = None
    skill_repos: list[SkillRepoConfig] | None = None
    base_image: str | None = None


class EnvironmentResponse(BaseModel):
    id: str
    name: str
    packages: dict = {}
    networking: dict = {}
    resource_limits: dict = {}
    repositories: list[dict] = []
    skill_repos: list[dict] = []
    base_image: str | None = None
    ip_subnet: str | None = None
    dockerfile_cache: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    archived_at: datetime | None = None

    model_config = {"from_attributes": True}


class EnvironmentListResponse(BaseModel):
    items: list[EnvironmentResponse]
    count: int
