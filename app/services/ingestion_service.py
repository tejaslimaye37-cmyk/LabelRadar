"""Ingestion pipeline coordinating openFDA retrieval, diffing, and dual-persistence."""


from sqlalchemy import select

from app.core.logging import logger
from app.db.postgres import PostgresManager, get_postgres_manager
from app.models.graph import (
    ChangedToEdge,
    ChangeType,
    DrugNode,
    LabelVersionNode,
    SectionNode,
)
from app.models.openfda import OpenFDALabelRecord
from app.models.schemas import IngestResponse, VersionSummary
from app.models.sql import DrugRecord, LabelSectionRecord, LabelVersionRecord, SectionDiffRecord
from app.services.differ import LabelDiffer, compute_sha256
from app.services.graph_service import GraphService, get_graph_service
from app.services.openfda_client import OpenFDAClient, get_openfda_client


class IngestionService:
    """Coordinates fetching from openFDA, section-by-section diffing, and saving to Neo4j + Postgres."""

    def __init__(
        self,
        openfda_client: OpenFDAClient | None = None,
        graph_service: GraphService | None = None,
        postgres_manager: PostgresManager | None = None,
    ):
        self.openfda = openfda_client or get_openfda_client()
        self.graph = graph_service or get_graph_service()
        self.pg = postgres_manager or get_postgres_manager()
        self.differ = LabelDiffer()

    async def ingest_drug(
        self,
        drug_name: str,
        spl_set_id: str | None = None,
        max_versions: int = 20,
    ) -> IngestResponse:
        """Main ingestion pipeline for a given drug."""
        clean_drug = drug_name.strip()
        logger.info("Starting ingestion pipeline for drug: %s (limit: %d)", clean_drug, max_versions)

        # 1. Fetch historical label versions from openFDA
        records: list[OpenFDALabelRecord] = await self.openfda.fetch_labels_for_drug(
            drug_name=clean_drug,
            spl_set_id=spl_set_id,
            limit=max_versions,
        )

        if not records:
            return IngestResponse(
                success=False,
                drug_name=clean_drug,
                versions_ingested=0,
                sections_created=0,
                diffs_computed=0,
                message=f"No label records found for '{clean_drug}'.",
            )

        # 2. Extract drug metadata from the first record
        first_rec = records[0]
        brand_name = first_rec.openfda.primary_brand_name or clean_drug
        generic_name = first_rec.openfda.primary_generic_name
        resolved_set_id = (
            spl_set_id
            or first_rec.set_id
            or (first_rec.openfda.spl_set_id[0] if first_rec.openfda.spl_set_id else None)
        )

        drug_node = DrugNode(
            name=clean_drug.upper(),
            brand_name=brand_name,
            generic_name=generic_name,
            spl_set_id=resolved_set_id,
        )

        # Persist drug in Neo4j
        await self.graph.upsert_drug(drug_node)

        # Persist drug in Postgres
        async with self.pg.get_session() as session:
            stmt = select(DrugRecord).where(DrugRecord.name == drug_node.name)
            res = await session.execute(stmt)
            existing_drug = res.scalar_one_or_none()
            if not existing_drug:
                pg_drug = DrugRecord(
                    name=drug_node.name,
                    brand_name=drug_node.brand_name,
                    generic_name=drug_node.generic_name,
                    spl_set_id=drug_node.spl_set_id,
                )
                session.add(pg_drug)
                await session.flush()
                drug_db_id = pg_drug.id
            else:
                existing_drug.brand_name = drug_node.brand_name or existing_drug.brand_name
                existing_drug.generic_name = drug_node.generic_name or existing_drug.generic_name
                existing_drug.spl_set_id = drug_node.spl_set_id or existing_drug.spl_set_id
                drug_db_id = existing_drug.id

        # 3. Store Versions and their Sections
        total_sections_created = 0
        version_summaries: list[VersionSummary] = []
        parsed_versions: list[dict] = []

        for idx, rec in enumerate(records):
            version_id = rec.id
            version_num = rec.version or str(idx + 1)
            effective_date = rec.effective_date_iso

            v_node = LabelVersionNode(
                version_id=version_id,
                version_number=version_num,
                effective_date=effective_date,
                spl_set_id=resolved_set_id,
            )
            await self.graph.upsert_version(drug_node.name, v_node)

            # Store in Postgres
            async with self.pg.get_session() as session:
                stmt = select(LabelVersionRecord).where(
                    LabelVersionRecord.version_id == version_id
                )
                res = await session.execute(stmt)
                existing_v = res.scalar_one_or_none()
                if not existing_v:
                    pg_v = LabelVersionRecord(
                        drug_id=drug_db_id,
                        version_id=version_id,
                        version_number=version_num,
                        effective_date=effective_date,
                        raw_json=rec.model_dump(exclude={"raw_sections"}),
                    )
                    session.add(pg_v)
                    await session.flush()
                    v_db_id = pg_v.id
                else:
                    v_db_id = existing_v.id

            sections_map = rec.get_all_sections()
            for sec_name, sec_text in sections_map.items():
                sec_id = f"{version_id}:{sec_name}"
                sec_hash = compute_sha256(sec_text)
                sec_node = SectionNode(
                    section_id=sec_id,
                    section_name=sec_name,
                    version_id=version_id,
                    text=sec_text,
                    text_hash=sec_hash,
                    char_count=len(sec_text),
                    status="active",
                )
                await self.graph.upsert_section(version_id, sec_node)

                # Postgres section
                async with self.pg.get_session() as session:
                    stmt = select(LabelSectionRecord).where(
                        LabelSectionRecord.version_id == v_db_id,
                        LabelSectionRecord.section_name == sec_name,
                    )
                    res = await session.execute(stmt)
                    existing_sec = res.scalar_one_or_none()
                    if not existing_sec:
                        session.add(
                            LabelSectionRecord(
                                version_id=v_db_id,
                                section_name=sec_name,
                                content=sec_text,
                                content_hash=sec_hash,
                                char_count=len(sec_text),
                            )
                        )

                total_sections_created += 1

            version_summaries.append(
                VersionSummary(
                    version_id=version_id,
                    version_number=version_num,
                    effective_date=effective_date,
                    section_count=len(sections_map),
                )
            )
            parsed_versions.append({
                "record": rec,
                "version_id": version_id,
                "version_num": version_num,
                "effective_date": effective_date,
                "sections": sections_map,
            })

        # 4. Diff Consecutive Versions Section-by-Section
        diffs_computed_count = 0
        for i in range(len(parsed_versions) - 1):
            v_curr = parsed_versions[i]
            v_next = parsed_versions[i + 1]

            diff_results = self.differ.diff_label_versions(
                old_sections=v_curr["sections"],
                new_sections=v_next["sections"],
                from_version=v_curr["version_num"],
                to_version=v_next["version_num"],
                include_unchanged=False,
            )

            for diff in diff_results:
                from_sec_id = f"{v_curr['version_id']}:{diff.section_name}"
                to_sec_id = f"{v_next['version_id']}:{diff.section_name}"

                # Ensure section nodes exist in graph even for added/removed stubs
                if diff.change_type == ChangeType.ADDED:
                    # Create absent placeholder node in v_curr for clean traversal
                    absent_node = SectionNode(
                        section_id=from_sec_id,
                        section_name=diff.section_name,
                        version_id=v_curr["version_id"],
                        text="",
                        text_hash="",
                        char_count=0,
                        status="absent",
                    )
                    await self.graph.upsert_section(v_curr["version_id"], absent_node)
                elif diff.change_type == ChangeType.REMOVED:
                    # Create removed placeholder node in v_next for clean traversal
                    removed_node = SectionNode(
                        section_id=to_sec_id,
                        section_name=diff.section_name,
                        version_id=v_next["version_id"],
                        text="",
                        text_hash="",
                        char_count=0,
                        status="removed",
                    )
                    await self.graph.upsert_section(v_next["version_id"], removed_node)

                # Create (:Section)-[:CHANGED_TO]->(:Section) edge
                edge = ChangedToEdge(
                    change_type=diff.change_type,
                    section_name=diff.section_name,
                    diff=diff.diff_text,
                    added_lines=diff.added_lines,
                    removed_lines=diff.removed_lines,
                    similarity_ratio=diff.similarity_ratio,
                    summary=diff.summary,
                    from_version_id=v_curr["version_id"],
                    to_version_id=v_next["version_id"],
                )
                await self.graph.link_section_change(from_sec_id, to_sec_id, edge)

                # Store diff in Postgres
                async with self.pg.get_session() as session:
                    session.add(
                        SectionDiffRecord(
                            drug_name=drug_node.name,
                            from_version_id=v_curr["version_id"],
                            to_version_id=v_next["version_id"],
                            section_name=diff.section_name,
                            change_type=diff.change_type.value,
                            diff_text=diff.diff_text,
                            added_lines=diff.added_lines,
                            removed_lines=diff.removed_lines,
                            similarity_ratio=diff.similarity_ratio,
                            summary=diff.summary,
                        )
                    )

                diffs_computed_count += 1

        logger.info(
            "Ingestion completed for %s: %d versions, %d sections, %d diffs",
            clean_drug,
            len(records),
            total_sections_created,
            diffs_computed_count,
        )

        return IngestResponse(
            success=True,
            drug_name=clean_drug.upper(),
            spl_set_id=resolved_set_id,
            versions_ingested=len(records),
            sections_created=total_sections_created,
            diffs_computed=diffs_computed_count,
            versions=version_summaries,
            message=f"Successfully ingested {len(records)} versions with {diffs_computed_count} section changes.",
        )


_ingestion_service: IngestionService | None = None


def get_ingestion_service() -> IngestionService:
    """Dependency provider for IngestionService."""
    global _ingestion_service
    if _ingestion_service is None:
        _ingestion_service = IngestionService(
            openfda_client=get_openfda_client(),
            graph_service=get_graph_service(),
            postgres_manager=get_postgres_manager(),
        )
    return _ingestion_service
