"""Neo4j graph database driver and connection lifecycle management."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import Depends
from neo4j import AsyncDriver, AsyncGraphDatabase, AsyncSession

from app.core.config import Settings, get_settings
from app.core.logging import logger


class Neo4jManager:
    """Manages async Neo4j driver connection and schema constraints."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._driver: AsyncDriver | None = None

    async def connect(self) -> AsyncDriver:
        """Initializes the Neo4j AsyncDriver."""
        if self._driver is None:
            logger.info("Initializing Neo4j driver at %s", self.settings.NEO4J_URI)
            self._driver = AsyncGraphDatabase.driver(
                self.settings.NEO4J_URI,
                auth=(self.settings.NEO4J_USER, self.settings.NEO4J_PASSWORD),
                max_connection_lifetime=self.settings.NEO4J_MAX_CONNECTION_LIFETIME,
                max_connection_pool_size=self.settings.NEO4J_MAX_CONNECTION_POOL_SIZE,
            )
        return self._driver

    async def close(self) -> None:
        """Closes the Neo4j driver pool."""
        if self._driver is not None:
            logger.info("Closing Neo4j driver...")
            await self._driver.close()
            self._driver = None

    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Async context manager for yielding a Neo4j session."""
        driver = await self.connect()
        async with driver.session(database=self.settings.NEO4J_DATABASE) as session:
            yield session

    async def init_schema(self) -> None:
        """Ensures uniqueness constraints and performance indexes exist in Neo4j."""
        constraint_queries = [
            # Unique drug node by normalized name
            """
            CREATE CONSTRAINT drug_name_unique IF NOT EXISTS
            FOR (d:Drug) REQUIRE d.name IS UNIQUE
            """,
            # Unique version node by version_id
            """
            CREATE CONSTRAINT version_id_unique IF NOT EXISTS
            FOR (v:LabelVersion) REQUIRE v.version_id IS UNIQUE
            """,
            # Unique section node by section_id
            """
            CREATE CONSTRAINT section_id_unique IF NOT EXISTS
            FOR (s:Section) REQUIRE s.section_id IS UNIQUE
            """,
            # Index on section name for fast timeline lookups
            """
            CREATE INDEX section_name_idx IF NOT EXISTS
            FOR (s:Section) ON (s.section_name)
            """,
        ]

        logger.info("Verifying Neo4j schema constraints and indexes...")
        try:
            async with self.get_session() as session:
                for query in constraint_queries:
                    await session.run(query)
            logger.info("Neo4j schema constraints initialized successfully.")
        except Exception as exc:
            logger.warning("Could not initialize Neo4j schema constraints (offline or starting up): %s", exc)

    async def verify_connectivity(self) -> bool:
        """Pings Neo4j to check health."""
        try:
            driver = await self.connect()
            await driver.verify_connectivity()
            return True
        except Exception as exc:
            logger.warning("Neo4j connectivity check failed: %s", exc)
            return False


_neo4j_manager: Neo4jManager | None = None


def get_neo4j_manager(settings: Settings = Depends(get_settings)) -> Neo4jManager:
    """Dependency provider / singleton for Neo4jManager."""
    global _neo4j_manager
    if _neo4j_manager is None or settings is not None:
        _neo4j_manager = Neo4jManager(settings=settings)
    return _neo4j_manager
