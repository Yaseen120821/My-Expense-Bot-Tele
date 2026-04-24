"""
Async database engine, session factory, and lifecycle management.
Uses SQLAlchemy 2.0 async with asyncpg driver.
Configured for Neon PostgreSQL with SSL.
"""

import ssl

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings
from app.utils.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Declarative base for all models
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""
    pass


# ---------------------------------------------------------------------------
# Engine & session factory (lazy — created on first call to init_db)
# ---------------------------------------------------------------------------

_engine = None
_async_session_factory = None


def _build_connect_args() -> dict:
    """
    Build connect_args for asyncpg.
    Neon PostgreSQL requires SSL — create an SSL context.
    """
    settings = get_settings()
    url = settings.DATABASE_URL

    # Neon and most cloud Postgres providers require SSL
    if "sslmode=require" in url or "sslmode=verify" in url:
        ssl_ctx = ssl.create_default_context()
        # Neon uses valid certs, but we don't have a local CA bundle check
        # server_hostname is handled automatically by asyncpg
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE
        return {"ssl": ssl_ctx}

    return {}


def _get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        connect_args = _build_connect_args()

        _engine = create_async_engine(
            settings.DATABASE_URL,
            echo=(not settings.is_production),
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            pool_recycle=300,
            connect_args=connect_args,
        )
        logger.info(f"Database engine created (pool_size=10, SSL={'ssl' in connect_args})")
    return _engine


def _get_session_factory():
    global _async_session_factory
    if _async_session_factory is None:
        _async_session_factory = async_sessionmaker(
            bind=_get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _async_session_factory


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def init_db() -> None:
    """Create all tables. Use for development / initial setup."""
    # Import models so they register on Base.metadata
    import app.models.user  # noqa: F401
    import app.models.expense  # noqa: F401

    engine = _get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created successfully")


async def close_db() -> None:
    """Dispose of the connection pool."""
    global _engine, _async_session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _async_session_factory = None
        logger.info("Database connection pool closed")


async def get_db() -> AsyncSession:
    """
    FastAPI dependency — yields an async session.

    Usage:
        @router.get("/")
        async def handler(db: AsyncSession = Depends(get_db)):
            ...
    """
    factory = _get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def get_session_factory():
    """Return the async session factory (for use outside FastAPI deps, e.g. scheduler)."""
    return _get_session_factory()
