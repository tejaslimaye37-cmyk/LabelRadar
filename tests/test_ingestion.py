"""Integration tests for IngestionService."""

from unittest.mock import AsyncMock

import pytest

from app.db.postgres import PostgresManager
from app.services.graph_service import GraphService
from app.services.ingestion_service import IngestionService
from app.services.openfda_client import OpenFDAClient


@pytest.mark.asyncio
async def test_ingest_drug_pipeline(
    mock_openfda_client: OpenFDAClient,
    mock_graph_service: GraphService,
    mock_postgres_manager: PostgresManager,
):
    service = IngestionService(
        openfda_client=mock_openfda_client,
        graph_service=mock_graph_service,
        postgres_manager=mock_postgres_manager,
    )

    result = await service.ingest_drug("Lipitor", max_versions=10)

    assert result.success is True
    assert result.drug_name == "LIPITOR"
    assert result.versions_ingested == 3
    assert result.diffs_computed > 0
    assert len(result.versions) == 3

    # Verify graph calls
    mock_graph_service.upsert_drug.assert_awaited()
    assert mock_graph_service.upsert_version.await_count == 3
    assert mock_graph_service.upsert_section.await_count > 0
    assert mock_graph_service.link_section_change.await_count > 0


@pytest.mark.asyncio
async def test_ingest_drug_empty_response(
    mock_graph_service: GraphService,
    mock_postgres_manager: PostgresManager,
):
    empty_client = AsyncMock(spec=OpenFDAClient)
    empty_client.fetch_labels_for_drug.return_value = []

    service = IngestionService(
        openfda_client=empty_client,
        graph_service=mock_graph_service,
        postgres_manager=mock_postgres_manager,
    )

    result = await service.ingest_drug("UnknownDrug")

    assert result.success is False
    assert result.versions_ingested == 0
    assert result.diffs_computed == 0
    assert "No label records found" in result.message
