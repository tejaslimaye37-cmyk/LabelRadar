"""Root API router assembling versioned endpoints."""

from fastapi import APIRouter

from app.api.v1.changes import router as changes_router
from app.api.v1.health import router as health_router
from app.api.v1.ingest import router as ingest_router

api_router = APIRouter()

api_router.include_router(health_router)
api_router.include_router(ingest_router)
api_router.include_router(changes_router)
