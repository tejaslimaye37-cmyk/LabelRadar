"""Drug label changes timeline endpoint."""


from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.logging import logger
from app.models.graph import ChangeType
from app.models.schemas import DrugChangesTimelineResponse
from app.services.graph_service import GraphService, get_graph_service

router = APIRouter(tags=["changes"])


@router.get("/changes", response_model=DrugChangesTimelineResponse)
async def get_drug_changes(
    drug_name: str = Query(..., description="Target drug brand or generic name (e.g. Lipitor)"),
    section_name: str | None = Query(
        None,
        description="Optional filter by section name (e.g. boxed_warning, contraindications)",
    ),
    change_type: ChangeType | None = Query(
        None,
        description="Optional filter by change type (added, removed, modified)",
    ),
    graph_service: GraphService = Depends(get_graph_service),
) -> DrugChangesTimelineResponse:
    """Returns the structured chronological timeline of label version changes and section diffs for a drug."""
    try:
        timeline = await graph_service.get_drug_change_timeline(
            drug_name=drug_name,
            section_name=section_name,
            change_type=change_type.value if change_type else None,
        )
        return timeline
    except Exception as exc:
        logger.exception("Failed to query change timeline for %s: %s", drug_name, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to query change timeline: {exc}",
        ) from exc
