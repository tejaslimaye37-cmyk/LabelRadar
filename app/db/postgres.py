"""PostgreSQL + pgvector connection and session management."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings, get_settings
from app.core.logging import logger
from app.models.sql import Base


class PostgresManager:
    """Manages SQLAlchemy async engine, sessions, and pgvector extension."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._engine: AsyncEngine | None = None
        self._sessionmaker: async_sessionmaker[AsyncSession] | None = None

    def get_engine(self) -> AsyncEngine:
        """Initializes or returns existing AsyncEngine."""
        if self._engine is None:
            url = self.settings.async_database_url
            logger.info("Creating async SQLAlchemy engine for %s:%d/%s",
                        self.settings.POSTGRES_HOST, self.settings.POSTGRES_PORT, self.settings.POSTGRES_DB)
            self._engine = create_async_engine(
                url,
                echo=self.settings.DEBUG,
                pool_pre_ping=True,
                pool_size=10,
                max_overflow=20,
            )
            self._sessionmaker = async_sessionmaker(
                self._engine,
                expire_on_commit=False,
                class_=AsyncSession,
            )
        return self._engine

    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Provides an async session within a transaction context."""
        self.get_engine()
        assert self._sessionmaker is not None
        async with self._sessionmaker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def init_db(self) -> None:
        """Enables pgvector extension and creates all database tables."""
        engine = self.get_engine()
        logger.info("Initializing PostgreSQL tables and pgvector extension...")
        try:
            async with engine.begin() as conn:
                # Enable vector extension
                await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
                # Create all tables defined in models.sql
                await conn.run_sync(Base.metadata.create_all)
            logger.info("PostgreSQL database tables initialized successfully.")
        except Exception as exc:
            logger.warning("Could not initialize PostgreSQL tables (offline or starting up): %s", exc)

    async def check_health(self) -> bool:
        """Pings Postgres database to verify connectivity."""
        try:
            async with self.get_session() as session:
                result = await session.execute(text("SELECT 1;"))
                return result.scalar() == 1
        except Exception as exc:
            logger.warning("Postgres health check failed: %s", exc)
            return False

    async def close(self) -> None:
        """Disposes engine connection pool."""
        if self._engine is not None:
            logger.info("Disposing PostgreSQL async engine...")
            await self._engine.dispose()
            self._engine = None
            self._sessionmaker = None


_postgres_manager: PostgresManager | None = None


def get_postgres_manager(settings: Settings = Depends(get_settings)) -> PostgresManager:
    """Dependency provider / singleton for PostgresManager."""
    global _postgres_manager
    if _postgres_manager is None or settings is not None:
        _postgres_manager = PostgresManager(settings=settings)
    return _postgres_manager


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI Depends generator for DB sessions."""
    manager = get_postgres_manager()
    async with manager.get_session() as session:
        yield session
