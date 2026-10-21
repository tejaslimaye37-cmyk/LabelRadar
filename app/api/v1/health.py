"""Health check endpoint."""

from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings
from app.db.neo4j import Neo4jManager, get_neo4j_manager
from app.db.postgres import PostgresManager, get_postgres_manager
from app.models.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def check_health(
    settings: Settings = Depends(get_settings),
    neo4j: Neo4jManager = Depends(get_neo4j_manager),
    postgres: PostgresManager = Depends(get_postgres_manager),
) -> HealthResponse:
    """Verifies service and database connectivity."""
    neo4j_ok = await neo4j.verify_connectivity()
    postgres_ok = await postgres.check_health()

    status = "healthy" if (neo4j_ok and postgres_ok) else "degraded"

    return HealthResponse(
        status=status,
        app=settings.APP_NAME,
        environment=settings.APP_ENV,
        databases={
            "neo4j": "connected" if neo4j_ok else "unreachable",
            "postgres": "connected" if postgres_ok else "unreachable",
        },
    )

