"""FastAPI app entry point — loaded by Aegra via aegra.json http.app.

Aegra takes this FastAPI instance and injects its own routers (Agent
Protocol endpoints) into it.  Lifespans are merged: Aegra's lifespan
runs first (DB, Redis, LangGraph service), then ours (platform DB
engine).

aegra.json:
{
  "http": {
    "app": "./src/custom_routes.py:app",
    "enable_custom_route_auth": true
  }
}
"""

# Monkey-patch langchain-mcp-adapters to strip 'id' from tool result content blocks.
# Fixes upstream bug: https://github.com/langchain-ai/langchain-mcp-adapters/issues/411
# The 'id' field added by langchain-core>=1.4.0 breaks validation in Fireworks,
# Mistral, and Anthropic APIs. Remove it before any MCP tool is called.
import langchain_mcp_adapters.tools as _lmcpt
_orig_convert = _lmcpt._convert_mcp_content_to_lc_block

def _patched_convert(content):
    result = _orig_convert(content)
    if isinstance(result, dict) and "id" in result:
        del result["id"]
    return result

_lmcpt._convert_mcp_content_to_lc_block = _patched_convert

import os
import sys

# Ensure ./src is on sys.path so subpackage imports work when Aegra
# loads this file as a standalone module (outside the dependencies path).
_src_dir = os.path.dirname(os.path.abspath(__file__))
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from routes.agents import router as agents_router
from routes.environments import router as environments_router
from routes.models import router as models_router
from routes.secrets import router as secrets_router
from routes.sessions import router as sessions_router
from routes.status import router as status_router
from routes.vaults import router as vaults_router


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Platform lifespan — initializes and tears down the platform DB engine.

    Aegra's own lifespan (database, Redis, LangGraph service) wraps this
    one, so by the time we run, Aegra is already fully initialized.
    """
    from db.engine import close_db, init_db

    await init_db()
    try:
        yield
    finally:
        await close_db()


app = FastAPI(
    title="Deep Agents Platform",
    description="Self-hosted Claude Managed Agents platform API",
    version="0.1.0",
    lifespan=lifespan,
)

# ── Public routes ──────────────────────────────────────────────────────
app.include_router(agents_router)
app.include_router(environments_router)
app.include_router(models_router)
app.include_router(sessions_router)
app.include_router(vaults_router)
app.include_router(secrets_router)

# ── Internal routes (called by factory graph) ─────────────────────────
app.include_router(status_router)
