"""Async HTTP client for querying openFDA Drug Label API."""

import io
import re
import urllib.parse
import zipfile
import xml.etree.ElementTree as ET

from datetime import datetime
from typing import Any

import httpx

from app.core.config import Settings, get_settings
from app.core.logging import logger
from app.models.openfda import OpenFDALabelRecord


class OpenFDAClientError(Exception):
    """Exception raised for openFDA API failures."""

    pass


class DrugNotFoundError(OpenFDAClientError):
    """Exception raised when openFDA finds no records for the given drug."""

    pass


def _build_openfda_url(
    base_url: str,
    search_query: str,
    limit: int,
    sort: str | None = None,
    api_key: str | None = None,
) -> str:
    """Builds the full openFDA URL with search params that preserve literal '+'.

    openFDA uses '+' as its boolean OR/AND operator within the 'search' param.
    httpx's params= kwarg percent-encodes '+' to '%2B', which openFDA rejects
    with a 404. We must build the URL string manually.
    """
    # URL-encode the non-search params normally
    other_params: dict[str, str] = {"limit": str(limit)}
    if sort:
        other_params["sort"] = sort
    if api_key:
        other_params["api_key"] = api_key

    qs_parts = [f"search={search_query}"]
    for k, v in other_params.items():
        qs_parts.append(f"{k}={urllib.parse.quote(v, safe=':')}")

    return f"{base_url}?{'&'.join(qs_parts)}"


class OpenFDAClient:
    """Async client interacting with openFDA's /drug/label.json endpoint."""

    def __init__(
        self,
        settings: Settings | None = None,
        http_client: httpx.AsyncClient | None = None,
    ):
        self.settings = settings or get_settings()
        self._external_client = http_client

    async def _get_client(self) -> httpx.AsyncClient:
        if self._external_client is not None:
            return self._external_client
        return httpx.AsyncClient(timeout=self.settings.OPENFDA_TIMEOUT_SECONDS)

    async def _fetch_dailymed_history(
        self,
        client: httpx.AsyncClient,
        set_id: str,
        limit: int,
    ) -> list[OpenFDALabelRecord]:
        """Download and parse historical SPL versions from DailyMed."""

        history_url = (
            "https://dailymed.nlm.nih.gov/dailymed/services/v2/"
            f"spls/{urllib.parse.quote(set_id, safe='')}/history.json"
        )

        logger.info(
            "DailyMed history versions: %s",
            [
                item.get("spl_version")
                for item in payload.get("data", {}).get("history", [])
            ],
        )
        
        response = await client.get(history_url)
        response.raise_for_status()

        payload = response.json()
        history = payload.get("data", {}).get("history", [])

        if not history:
            logger.warning(
                "DailyMed returned no history for SPL set ID %s", set_id
            )
            return []

        # Select the newest N versions, then process chronologically.
        history = sorted(
            history,
            key=lambda item: int(item.get("spl_version", "0") or 0),
            reverse=True,
        )[:max(1, min(limit, 100))]

        records: list[OpenFDALabelRecord] = []

        def local_name(tag: str) -> str:
            return tag.rsplit("}", 1)[-1]

        for entry in history:
            version = str(entry.get("spl_version", "")).strip()
            if not version:
                continue

            download_url = (
                "https://dailymed.nlm.nih.gov/dailymed/getFile.cfm"
            )

            try:
                download = await client.get(
                    download_url,
                    params={
                        "type": "zip",
                        "setid": set_id,
                        "version": version,
                    },
                )
                download.raise_for_status()

                with zipfile.ZipFile(io.BytesIO(download.content)) as archive:
                    xml_files = [
                        name for name in archive.namelist()
                        if name.lower().endswith(".xml")
                    ]

                    if not xml_files:
                        logger.warning(
                            "No XML found for SPL version %s", version
                        )
                        continue

                    root = ET.fromstring(archive.read(xml_files[0]))

            except (
                httpx.HTTPError,
                zipfile.BadZipFile,
                ET.ParseError,
                OSError,
            ) as exc:
                logger.warning(
                    "Could not download/parse SPL version %s: %s",
                    version,
                    exc,
                )
                continue

            def first_element(name: str):
                return next(
                    (
                        element
                        for element in root.iter()
                        if local_name(element.tag) == name
                    ),
                    None,
                )

            # Prefer the explicit SPL document version/date.
            version_element = first_element("versionNumber")
            effective_element = first_element("effectiveTime")

            actual_version = (
                version_element.attrib.get("value")
                if version_element is not None
                else None
            ) or version

            effective_time = (
                effective_element.attrib.get("value")
                if effective_element is not None
                else None
            )

            if effective_time:
                effective_time = effective_time[:8]

            if not effective_time:
                try:
                    effective_time = datetime.strptime(
                        entry.get("published_date", ""),
                        "%b %d, %Y",
                    ).strftime("%Y%m%d")
                except (ValueError, TypeError):
                    effective_time = None

            # Extract sections and retain their text for the existing diff engine.
            sections: dict[str, list[str]] = {}

            for element in root.iter():
                if local_name(element.tag) != "section":
                    continue

                title = next(
                    (
                        child for child in element
                        if local_name(child.tag) == "title"
                    ),
                    None,
                )

                code = next(
                    (
                        child for child in element
                        if local_name(child.tag) == "code"
                    ),
                    None,
                )

                name = (title.text or "").strip() if title is not None else ""

                if not name and code is not None:
                    name = code.attrib.get("displayName", "").strip()

                if not name:
                    continue

                text = "\n".join(
                    chunk.strip()
                    for chunk in element.itertext()
                    if chunk and chunk.strip()
                )

                if not text:
                    continue

                section_key = (
                    re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
                    or "section"
                )

                # Merge duplicate section names rather than silently losing text.
                sections.setdefault(section_key, []).append(text)

            # Keep the document identifier unique for each historical version.
            record_id = f"{set_id}-v{version}"

            record_data = {
                "id": record_id,
                "set_id": set_id,
                "version": actual_version,
                "effective_time": effective_time,
                "openfda": {
                    "spl_set_id": [set_id],
                    "spl_id": [record_id],
                },
                **{
                    key: value
                    for key, value in sections.items()
                },
            }

            try:
                records.append(
                    OpenFDALabelRecord.model_validate(record_data)
                )
            except Exception:
                logger.exception(
                    "Failed to normalize SPL version %s", version
                )

        records.sort(
            key=lambda record: (
                record.effective_time or "00000000",
                int(record.version)
                if record.version and record.version.isdigit()
                else 0,
            )
        )

        logger.info(
            "DailyMed returned %d parsed versions for set ID %s",
            len(records),
            set_id,
        )

        return records

    async def fetch_labels_for_drug(
        self,
        drug_name: str,
        spl_set_id: str | None = None,
        limit: int = 20,
    ) -> list[OpenFDALabelRecord]:
        """Queries openFDA for drug label records and returns parsed versions chronologically."""
        clean_drug = drug_name.strip()
        has_valid_set_id = bool(
            spl_set_id
            and spl_set_id.strip()
            and spl_set_id.strip().lower() != "string"
        )

        # Build openFDA search expression.
        # openFDA uses literal '+' as a space / implicit-OR inside the search field,
        # and ' OR ' (space-OR-space) as an explicit OR between clauses.
        if has_valid_set_id:
            search_query = f'openfda.spl_set_id:"{spl_set_id.strip()}"'
        else:
            escaped_drug = clean_drug.replace('"', '\\"')
            # Use ' OR ' (with literal spaces) so httpx won't break it.
            search_query = (
                f'openfda.brand_name:"{escaped_drug}"'
                f" OR "
                f'openfda.generic_name:"{escaped_drug}"'
                f" OR "
                f'openfda.substance_name:"{escaped_drug}"'
            )

        logger.info("Querying openFDA: search=%s (limit=%d)", search_query, limit)

        # Build URL manually to preserve '+' and ' OR ' semantics
        full_url = _build_openfda_url(
            base_url=self.settings.OPENFDA_BASE_URL,
            search_query=search_query,
            limit=min(limit, 100),
            sort="effective_time:asc",
            api_key=self.settings.OPENFDA_API_KEY or None,
        )

        client = await self._get_client()
        should_close = self._external_client is None

        try:
            response = await client.get(full_url)

            if response.status_code == 404:
                logger.warning("No labels found on openFDA for drug: %s", clean_drug)
                raise DrugNotFoundError(
                    f"No openFDA label records found for drug '{clean_drug}'"
                )

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

            records: list[OpenFDALabelRecord] = []

            for item in raw_results:
                try:
                    records.append(OpenFDALabelRecord.model_validate(item))
                except Exception as e:
                    logger.warning("Failed to parse an openFDA record: %s", e)

            # If an SPL set ID is known and OpenFDA returns at most one
            # version, try retrieving the full version history from DailyMed.
            resolved_set_id = (
                spl_set_id.strip()
                if has_valid_set_id
                else (
                    records[0].set_id
                    or (
                        records[0].openfda.spl_set_id[0]
                        if records[0].openfda.spl_set_id
                        else None
                    )
                    if records
                    else None
                )
            )

            if resolved_set_id and (has_valid_set_id or len(records) <= 1):
                try:
                    historical_records = await self._fetch_dailymed_history(
                        client=client,
                        set_id=resolved_set_id,
                        limit=limit,
                    )

                    if len(historical_records) > len(records):
                        records = historical_records

                except (httpx.HTTPError, ValueError, KeyError) as exc:
                    logger.warning(
                        "DailyMed history lookup failed for %s: %s",
                        resolved_set_id,
                        exc,
                    )

            if not records:
                raise DrugNotFoundError(
                    f"No usable label records found for drug '{clean_drug}'"
                )

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

            logger.info(
                "openFDA returned %d distinct records for '%s'",
                len(distinct_records),
                clean_drug,
            )
            return distinct_records

        except httpx.RequestError as exc:
            logger.error("HTTP network error querying openFDA: %s", exc)
            raise OpenFDAClientError(f"Network error querying openFDA: {exc}") from exc
        finally:
            if should_close:
                await client.aclose()


_openfda_client: OpenFDAClient | None = None


def get_openfda_client() -> OpenFDAClient:
    """Dependency provider for OpenFDAClient."""
    global _openfda_client
    if _openfda_client is None:
        _openfda_client = OpenFDAClient(settings=get_settings())
    return _openfda_client
