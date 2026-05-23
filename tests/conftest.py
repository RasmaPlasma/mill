"""Shared test fixtures using PostgreSQL via testcontainers.

All requests within a single test share the same database session so that
data created by POST is visible to subsequent GET/PATCH calls. The session
is rolled back at the end of each test.
"""

import os

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

# Set PLATFORM_MASTER_KEY before importing db modules
os.environ.setdefault(
    "PLATFORM_MASTER_KEY",
    "0000000000000000000000000000000000000000000000000000000000000000",
)

from db.models import Base  # noqa: E402


@pytest.fixture(scope="session")
def postgres_url():
    """Spin up a PostgreSQL container for the entire test session."""
    container = PostgresContainer("postgres:16-alpine")
    container.start()
    raw_url = container.get_connection_url()
    # Ensure asyncpg driver — replace any existing driver prefix
    if raw_url.startswith("postgresql+psycopg2://"):
        url = raw_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)
    elif raw_url.startswith("postgresql://"):
        url = raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    else:
        url = raw_url
    yield url
    container.stop()


@pytest_asyncio.fixture
async def engine(postgres_url):
    """Create a fresh async PostgreSQL engine per test."""
    eng = create_async_engine(postgres_url, echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Also initialize the global db.engine so _save_event (which calls
    # get_session_factory() outside FastAPI DI) works in tests.
    os.environ["DATABASE_URL"] = postgres_url
    from db.engine import init_db, close_db
    await init_db()

    yield eng

    await close_db()
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await eng.dispose()


@pytest_asyncio.fixture
async def session(engine):
    """Yield an AsyncSession that rolls back after each test."""
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as sess:
        yield sess
        await sess.rollback()


@pytest_asyncio.fixture
async def client(session):
    """Yield an httpx AsyncClient wired to the FastAPI app.

    All requests within a single test share ONE database session (the
    ``session`` fixture). Data created by POST is visible to subsequent
    GET/PATCH because they all use the same underlying SQLAlchemy session.
    The session is rolled back when the test ends.
    """
    from custom_routes import app
    from db.engine import get_db

    async def _override_get_db():
        yield session

    app.dependency_overrides[get_db] = _override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def llm_model(client):
    """Create a default LLMModel for tests that need an agent with a model."""
    resp = await client.post(
        "/v1/models",
        json={
            "display_name": "Test Model",
            "provider": "fireworks",
            "provider_model": "accounts/fireworks/models/test",
        },
    )
    assert resp.status_code == 201
    return resp.json()
