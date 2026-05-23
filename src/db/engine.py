"""Async SQLAlchemy engine and session factory for the platform database.

Uses asyncpg driver for async PostgreSQL access. Connection URL is read
from PLATFORM_DATABASE_URL (falls back to DATABASE_URL for dev).

Usage in FastAPI routes:
    async with get_db() as session:
        result = await session.execute(select(Agent))

Usage in lifespan:
    await init_db()  # startup
    await close_db()  # shutdown
"""

import os

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _get_database_url() -> str:
    raw = os.environ.get("PLATFORM_DATABASE_URL") or os.environ.get("DATABASE_URL", "")
    if not raw:
        raise RuntimeError(
            "DATABASE_URL or PLATFORM_DATABASE_URL environment variable is required"
        )
    # Ensure we use the asyncpg driver
    if raw.startswith("postgresql://"):
        return raw.replace("postgresql://", "postgresql+asyncpg://", 1)
    if raw.startswith("postgresql+asyncpg://"):
        return raw
    raise ValueError(
        f"Unsupported DATABASE_URL scheme. Expected postgresql:// or "
        f"postgresql+asyncpg://, got: {raw.split('://')[0]}://"
    )


async def init_db() -> None:
    """Initialize the async engine and session factory. Call once at startup."""
    global _engine, _session_factory
    url = _get_database_url()
    _engine = create_async_engine(
        url,
        echo=False,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
    )
    _session_factory = async_sessionmaker(
        _engine,
        expire_on_commit=False,
    )


async def close_db() -> None:
    """Dispose of the engine. Call once at shutdown."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None


async def get_db():
    """FastAPI dependency that yields an async database session.

    Usage:
        @router.get("/items")
        async def list_items(db: AsyncSession = Depends(get_db)):
            ...
    """
    if _session_factory is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    async with _session_factory() as session:
        session.sync_session.expire_on_flush = False
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the session factory for use outside FastAPI dependency injection.

    Raises RuntimeError if the database has not been initialized.
    """
    if _session_factory is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _session_factory
