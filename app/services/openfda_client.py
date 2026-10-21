"""Async HTTP client for querying openFDA Drug Label API."""

from typing import Any

import httpx
from fastapi import Depends

from app.core.config import Settings, get_settings
from app.core.logging import logger
from app.models.openfda import OpenFDALabelRecord


class OpenFDAClientError(Exception):
    """Exception raised for openFDA API failures."""
    pass


class DrugNotFoundError(OpenFDAClientError):
    """Exception raised when openFDA finds no records for the given drug."""
    pass


class OpenFDAClient:
    """Async client interacting with openFDA's /drug/label.json endpoint."""

    def __init__(self, settings: Settings | None = None, http_client: httpx.AsyncClient | None = None):
        self.settings = settings or get_settings()
        self._external_client = http_client

    async def _get_client(self) -> httpx.AsyncClient:
        if self._external_client is not None:
            return self._external_client
        return httpx.AsyncClient(timeout=self.settings.OPENFDA_TIMEOUT_SECONDS)

    async def fetch_labels_for_drug(
        self,
        drug_name: str,
        spl_set_id: str | None = None,
        limit: int = 20,
    ) -> list[OpenFDALabelRecord]:
        """Queries openFDA for drug label records and returns parsed versions chronologically."""
        clean_drug = drug_name.strip()
        has_valid_set_id = bool(spl_set_id and spl_set_id.strip() and spl_set_id.strip().lower() != "string")

        # Build openFDA search expression
        if has_valid_set_id:
            search_query = f'openfda.spl_set_id:"{spl_set_id.strip()}"'
        else:
            # Match brand_name, generic_name, or substance_name
            escaped_drug = clean_drug.replace('"', '\\"')
            search_query = (
                f'(openfda.brand_name:"{escaped_drug}"+'
                f'openfda.generic_name:"{escaped_drug}"+'
                f'openfda.substance_name:"{escaped_drug}")'
            )

        params: dict[str, Any] = {
            "search": search_query,
            "limit": min(limit, 100),
            "sort": "effective_time:asc",
        }
        if self.settings.OPENFDA_API_KEY:
            params["api_key"] = self.settings.OPENFDA_API_KEY

        url = self.settings.OPENFDA_BASE_URL
        logger.info("Querying openFDA: %s with search=%s", url, search_query)

        client = await self._get_client()
        should_close = self._external_client is None

        try:
            response = await client.get(url, params=params)

            if response.status_code == 404:
                logger.warning("No labels found on openFDA for drug: %s", clean_drug)
                raise DrugNotFoundError(f"No openFDA label records found for drug '{clean_drug}'")

            if response.status_code != 200:
                logger.error(
                    "openFDA returned error status %d: %s",
                    response.status_code,
                    response.text[:300],
                )
                raise OpenFDAClientError(
                    f"openFDA error HTTP {response.status_code}: {response.text[:200]}"
                )

            data = response.json()
            raw_results = data.get("results", [])
            if not raw_results:
                raise DrugNotFoundError(f"Empty results for drug '{clean_drug}'")

            records: list[OpenFDALabelRecord] = []
            for item in raw_results:
                try:
                    records.append(OpenFDALabelRecord.model_validate(item))
                except Exception as e:
                    logger.warning("Failed to parse an openFDA record: %s", e)

            # Sort chronologically by effective_time, then version
            records.sort(
                key=lambda r: (
                    r.effective_time or "00000000",
                    int(r.version) if (r.version and r.version.isdigit()) else 0,
                    r.id,
                )
            )

            # Deduplicate records by unique id
            seen_ids: set[str] = set()
            distinct_records: list[OpenFDALabelRecord] = []
            for rec in records:
                if rec.id not in seen_ids:
                    seen_ids.add(rec.id)
                    distinct_records.append(rec)

            return distinct_records

        except httpx.RequestError as exc:
            logger.error("HTTP network error querying openFDA: %s", exc)
            raise OpenFDAClientError(f"Network error querying openFDA: {exc}") from exc
        finally:
            if should_close:
                await client.aclose()


_openfda_client: OpenFDAClient | None = None


def get_openfda_client(settings: Settings = Depends(get_settings)) -> OpenFDAClient:
    """Dependency provider for OpenFDAClient."""
    global _openfda_client
    if _openfda_client is None or settings is not None:
        _openfda_client = OpenFDAClient(settings=settings)
    return _openfda_client
