"""Drug label ingestion endpoint."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.logging import logger
from app.models.schemas import IngestRequest, IngestResponse
from app.services.ingestion_service import IngestionService, get_ingestion_service
from app.services.openfda_client import DrugNotFoundError, OpenFDAClientError

router = APIRouter(tags=["ingestion"])


@router.post("/ingest", response_model=IngestResponse, status_code=status.HTTP_200_OK)
async def ingest_drug_labels(
    request: IngestRequest,
    service: IngestionService = Depends(get_ingestion_service),
) -> IngestResponse:
    """Ingests historical label versions for a given drug from openFDA, diffs them, and constructs the graph."""
    try:
        response = await service.ingest_drug(
            drug_name=request.drug_name,
            spl_set_id=request.spl_set_id,
            max_versions=request.max_versions,
        )
        return response
    except DrugNotFoundError as exc:
        logger.warning("Ingest drug not found: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except OpenFDAClientError as exc:
        logger.error("OpenFDA upstream error during ingestion: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"openFDA upstream API error: {exc}",
        ) from exc
    except Exception as exc:
        logger.exception("Unexpected error during ingestion: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ingestion failed: {exc}",
        ) from exc
