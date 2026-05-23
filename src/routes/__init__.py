"""Route re-exports — all API routers for the platform."""

from routes.agents import router as agents_router
from routes.environments import router as environments_router
from routes.secrets import router as secrets_router
from routes.sessions import router as sessions_router
from routes.status import router as status_router
from routes.vaults import router as vaults_router

__all__ = [
    "agents_router",
    "environments_router",
    "secrets_router",
    "sessions_router",
    "status_router",
    "vaults_router",
]
