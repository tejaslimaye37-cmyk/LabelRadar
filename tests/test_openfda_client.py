"""Unit tests for OpenFDAClient with respx mocked HTTP responses."""

import httpx
import pytest
import respx

from app.core.config import Settings
from app.services.openfda_client import DrugNotFoundError, OpenFDAClient, OpenFDAClientError
from tests.fixtures.openfda_responses import MOCK_OPENFDA_LIPITOR_RESPONSE


@pytest.mark.asyncio
async def test_fetch_labels_success(test_settings: Settings):
    with respx.mock(base_url="https://api.fda.gov") as respx_mock:
        respx_mock.get("/drug/label.json").respond(
            status_code=200,
            json=MOCK_OPENFDA_LIPITOR_RESPONSE,
        )

        async with httpx.AsyncClient() as client:
            openfda_client = OpenFDAClient(settings=test_settings, http_client=client)
            records = await openfda_client.fetch_labels_for_drug("Lipitor")

            assert len(records) == 3
            # Chronological order verified
            assert records[0].effective_time == "20210115"
            assert records[1].effective_time == "20220610"
            assert records[2].effective_time == "20231120"
            assert records[0].openfda.primary_brand_name == "LIPITOR"


@pytest.mark.asyncio
async def test_fetch_labels_not_found(test_settings: Settings):
    with respx.mock(base_url="https://api.fda.gov") as respx_mock:
        respx_mock.get("/drug/label.json").respond(
            status_code=404,
            json={"error": {"code": "NOT_FOUND", "message": "No matches found!"}},
        )

        async with httpx.AsyncClient() as client:
            openfda_client = OpenFDAClient(settings=test_settings, http_client=client)
            with pytest.raises(DrugNotFoundError) as exc_info:
                await openfda_client.fetch_labels_for_drug("UnknownDrugName999")

            assert "UnknownDrugName999" in str(exc_info.value)


@pytest.mark.asyncio
async def test_fetch_labels_upstream_server_error(test_settings: Settings):
    with respx.mock(base_url="https://api.fda.gov") as respx_mock:
        respx_mock.get("/drug/label.json").respond(
            status_code=500,
            text="Internal Server Error",
        )

        async with httpx.AsyncClient() as client:
            openfda_client = OpenFDAClient(settings=test_settings, http_client=client)
            with pytest.raises(OpenFDAClientError) as exc_info:
                await openfda_client.fetch_labels_for_drug("Lipitor")

            assert "500" in str(exc_info.value)


@pytest.mark.asyncio
async def test_fetch_labels_with_spl_set_id(test_settings: Settings):
    with respx.mock(base_url="https://api.fda.gov") as respx_mock:
        route = respx_mock.get("/drug/label.json").respond(
            status_code=200,
            json=MOCK_OPENFDA_LIPITOR_RESPONSE,
        )

        async with httpx.AsyncClient() as client:
            openfda_client = OpenFDAClient(settings=test_settings, http_client=client)
            await openfda_client.fetch_labels_for_drug(
                "Lipitor", spl_set_id="spl-set-lipitor-001"
            )

            assert route.called
            called_params = route.calls.last.request.url.params
            assert 'openfda.spl_set_id:"spl-set-lipitor-001"' in called_params["search"]

