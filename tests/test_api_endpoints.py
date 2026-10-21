"""End-to-end API tests for LabelRadar endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_endpoint(app_client: AsyncClient):
    response = await app_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["app"] == "LabelRadar-Test"
    assert data["databases"]["neo4j"] == "connected"
    assert data["databases"]["postgres"] == "connected"


@pytest.mark.asyncio
async def test_ingest_endpoint_success(app_client: AsyncClient):
    payload = {
        "drug_name": "Lipitor",
        "max_versions": 5,
    }
    response = await app_client.post("/ingest", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["drug_name"] == "LIPITOR"
    assert data["versions_ingested"] == 3
    assert data["diffs_computed"] > 0
    assert len(data["versions"]) == 3


@pytest.mark.asyncio
async def test_changes_endpoint_success(app_client: AsyncClient):
    # Ingest first to populate graph
    await app_client.post("/ingest", json={"drug_name": "Lipitor"})

    response = await app_client.get("/changes?drug_name=Lipitor")
    assert response.status_code == 200
    data = response.json()
    assert data["drug_name"] == "LIPITOR"
    assert data["total_versions"] >= 3
    assert len(data["timeline"]) >= 1

    # Check structure of the transitions
    first_transition = data["timeline"][0]
    assert "from_version_id" in first_transition
    assert "to_version_id" in first_transition
    assert len(first_transition["changes"]) > 0

    first_change = first_transition["changes"][0]
    assert "section_name" in first_change
    assert "change_type" in first_change
    assert "diff" in first_change


@pytest.mark.asyncio
async def test_changes_endpoint_filter_by_section(app_client: AsyncClient):
    await app_client.post("/ingest", json={"drug_name": "Lipitor"})

    response = await app_client.get("/changes?drug_name=Lipitor&section_name=boxed_warning")
    assert response.status_code == 200
    data = response.json()
    assert data["drug_name"] == "LIPITOR"
    for transition in data["timeline"]:
        for change in transition["changes"]:
            assert change["section_name"] == "boxed_warning"


@pytest.mark.asyncio
async def test_ingest_endpoint_drug_not_found(
    app_client: AsyncClient,
    mock_openfda_client,
):
    from app.services.openfda_client import DrugNotFoundError

    mock_openfda_client.fetch_labels_for_drug.side_effect = DrugNotFoundError("Drug not found")
    response = await app_client.post("/ingest", json={"drug_name": "NonExistentDrug"})
    assert response.status_code == 404
    assert "Drug not found" in response.json()["detail"]


@pytest.mark.asyncio
async def test_ingest_endpoint_upstream_error(
    app_client: AsyncClient,
    mock_openfda_client,
):
    from app.services.openfda_client import OpenFDAClientError

    mock_openfda_client.fetch_labels_for_drug.side_effect = OpenFDAClientError("Upstream 500 error")
    response = await app_client.post("/ingest", json={"drug_name": "FailingDrug"})
    assert response.status_code == 502
    assert "openFDA upstream API error" in response.json()["detail"]


@pytest.mark.asyncio
async def test_changes_endpoint_server_error(
    app_client: AsyncClient,
    mock_graph_service,
):
    mock_graph_service.get_drug_change_timeline.side_effect = RuntimeError("Database offline")
    response = await app_client.get("/changes?drug_name=Lipitor")
    assert response.status_code == 500
    assert "Database offline" in response.json()["detail"]
