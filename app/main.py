"""LabelRadar FastAPI application entrypoint."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import get_settings
from app.core.logging import logger, setup_logging
from app.db.neo4j import get_neo4j_manager
from app.db.postgres import get_postgres_manager


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manages application lifecycle: database startup and cleanup."""
    settings = get_settings()
    setup_logging(debug=settings.DEBUG)
    logger.info("Starting up %s (env: %s)...", settings.APP_NAME, settings.APP_ENV)

    # Initialize Neo4j schema
    neo4j = get_neo4j_manager()
    await neo4j.init_schema()

    # Initialize PostgreSQL tables and pgvector extension
    postgres = get_postgres_manager()
    await postgres.init_db()

    yield

    logger.info("Shutting down %s...", settings.APP_NAME)
    await neo4j.close()
    await postgres.close()
    logger.info("Shutdown complete.")


def create_application() -> FastAPI:
    """Application factory for LabelRadar."""
    settings = get_settings()

    application = FastAPI(
        title="LabelRadar API",
        description="Regulatory drug label-change intelligence platform powered by openFDA, Neo4j, and pgvector.",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # CORS configuration
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount API routes
    application.include_router(api_router, prefix=settings.API_V1_PREFIX)
    # Also mount directly at root for convenience (/ingest, /changes, /health)
    application.include_router(api_router)

    @application.get("/", tags=["root"])
    async def root() -> dict[str, Any]:
        """Root endpoint with service metadata and documentation links."""
        return {
            "service": settings.APP_NAME,
            "version": "0.1.0",
            "description": "Regulatory drug label-change intelligence platform",
            "docs_url": "/docs",
            "health_url": "/health",
            "endpoints": {
                "ingest": "POST /ingest",
                "changes": "GET /changes?drug_name={drug_name}",
            },
        }

    return application


app = create_application()
