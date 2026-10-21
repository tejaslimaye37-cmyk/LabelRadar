"""Neo4j graph service managing Drug, LabelVersion, and Section nodes and diff edges."""


from fastapi import Depends

from app.db.neo4j import Neo4jManager, get_neo4j_manager
from app.models.graph import ChangedToEdge, DrugNode, LabelVersionNode, SectionNode
from app.models.schemas import (
    DrugChangesTimelineResponse,
    SectionChangeDetail,
    VersionTransition,
)


class GraphService:
    """Encapsulates all Neo4j graph operations for LabelRadar."""

    def __init__(self, manager: Neo4jManager | None = None):
        self.manager = manager or get_neo4j_manager()

    async def upsert_drug(self, drug: DrugNode) -> None:
        """Creates or updates a (:Drug) node."""
        query = """
        MERGE (d:Drug {name: $name})
        ON CREATE SET d.brand_name = $brand_name,
                      d.generic_name = $generic_name,
                      d.spl_set_id = $spl_set_id,
                      d.created_at = datetime()
        ON MATCH SET d.brand_name = coalesce($brand_name, d.brand_name),
                     d.generic_name = coalesce($generic_name, d.generic_name),
                     d.spl_set_id = coalesce($spl_set_id, d.spl_set_id),
                     d.updated_at = datetime()
        """
        async with self.manager.get_session() as session:
            await session.run(
                query,
                name=drug.name.upper(),
                brand_name=drug.brand_name,
                generic_name=drug.generic_name,
                spl_set_id=drug.spl_set_id,
            )

    async def upsert_version(self, drug_name: str, version: LabelVersionNode) -> None:
        """Creates (:LabelVersion) and links (:Drug)-[:HAS_VERSION]->(:LabelVersion)."""
        query = """
        MATCH (d:Drug {name: $drug_name})
        MERGE (v:LabelVersion {version_id: $version_id})
        ON CREATE SET v.version_number = $version_number,
                      v.effective_date = $effective_date,
                      v.spl_set_id = $spl_set_id,
                      v.created_at = datetime()
        ON MATCH SET v.effective_date = coalesce($effective_date, v.effective_date),
                     v.spl_set_id = coalesce($spl_set_id, v.spl_set_id)
        MERGE (d)-[:HAS_VERSION]->(v)
        """
        async with self.manager.get_session() as session:
            await session.run(
                query,
                drug_name=drug_name.upper(),
                version_id=version.version_id,
                version_number=version.version_number,
                effective_date=version.effective_date,
                spl_set_id=version.spl_set_id,
            )

    async def upsert_section(self, version_id: str, section: SectionNode) -> None:
        """Creates (:Section) and links (:LabelVersion)-[:HAS_SECTION]->(:Section)."""
        query = """
        MATCH (v:LabelVersion {version_id: $version_id})
        MERGE (s:Section {section_id: $section_id})
        ON CREATE SET s.section_name = $section_name,
                      s.version_id = $version_id,
                      s.text = $text,
                      s.text_hash = $text_hash,
                      s.char_count = $char_count,
                      s.status = $status,
                      s.created_at = datetime()
        ON MATCH SET s.text = $text,
                     s.text_hash = $text_hash,
                     s.char_count = $char_count,
                     s.status = $status
        MERGE (v)-[:HAS_SECTION]->(s)
        """
        async with self.manager.get_session() as session:
            await session.run(
                query,
                version_id=version_id,
                section_id=section.section_id,
                section_name=section.section_name,
                text=section.text,
                text_hash=section.text_hash,
                char_count=section.char_count,
                status=section.status,
            )

    async def link_section_change(
        self,
        from_section_id: str,
        to_section_id: str,
        edge: ChangedToEdge,
    ) -> None:
        """Creates (:Section)-[:CHANGED_TO]->(:Section) carrying change_type, diff, and metrics."""
        query = """
        MATCH (s1:Section {section_id: $from_section_id})
        MATCH (s2:Section {section_id: $to_section_id})
        MERGE (s1)-[r:CHANGED_TO]->(s2)
        SET r.change_type = $change_type,
            r.section_name = $section_name,
            r.diff = $diff,
            r.added_lines = $added_lines,
            r.removed_lines = $removed_lines,
            r.similarity_ratio = $similarity_ratio,
            r.summary = $summary,
            r.updated_at = datetime()
        """
        async with self.manager.get_session() as session:
            await session.run(
                query,
                from_section_id=from_section_id,
                to_section_id=to_section_id,
                change_type=edge.change_type.value,
                section_name=edge.section_name,
                diff=edge.diff,
                added_lines=edge.added_lines,
                removed_lines=edge.removed_lines,
                similarity_ratio=edge.similarity_ratio,
                summary=edge.summary,
            )

    async def get_drug_change_timeline(
        self,
        drug_name: str,
        section_name: str | None = None,
        change_type: str | None = None,
    ) -> DrugChangesTimelineResponse:
        """Queries graph to return chronological version transitions and section diffs."""
        normalized_name = drug_name.strip().upper()

        # Query total versions count for metadata
        count_query = """
        MATCH (d:Drug {name: $drug_name})-[:HAS_VERSION]->(v:LabelVersion)
        RETURN count(v) AS total_versions, d.spl_set_id AS spl_set_id
        """

        timeline_query = """
        MATCH (d:Drug {name: $drug_name})-[:HAS_VERSION]->(v1:LabelVersion)-[:HAS_SECTION]->(s1:Section)-[r:CHANGED_TO]->(s2:Section)<-[:HAS_SECTION]-(v2:LabelVersion)<-[:HAS_VERSION]-(d)
        WHERE ($section_name IS NULL OR r.section_name = $section_name)
          AND ($change_type IS NULL OR r.change_type = $change_type)
          AND r.change_type <> 'unchanged'
        RETURN v1.version_id AS from_version_id,
               v1.version_number AS from_version_number,
               v2.version_id AS to_version_id,
               v2.version_number AS to_version_number,
               v2.effective_date AS effective_date,
               r.section_name AS section_name,
               r.change_type AS change_type,
               r.diff AS diff,
               r.added_lines AS added_lines,
               r.removed_lines AS removed_lines,
               r.similarity_ratio AS similarity_ratio,
               r.summary AS summary
        ORDER BY v2.effective_date ASC, v1.version_number ASC, r.section_name ASC
        """

        async with self.manager.get_session() as session:
            count_res = await session.run(count_query, drug_name=normalized_name)
            count_rec = await count_res.single()
            total_versions = count_rec["total_versions"] if count_rec else 0
            spl_set_id = count_rec["spl_set_id"] if count_rec else None

            res = await session.run(
                timeline_query,
                drug_name=normalized_name,
                section_name=section_name,
                change_type=change_type,
            )
            records = [record.data() async for record in res]

        # Group transitions by (from_version_id, to_version_id)
        transitions_map: dict[tuple[str, str], VersionTransition] = {}
        total_changes = 0

        for r in records:
            key = (r["from_version_id"], r["to_version_id"])
            if key not in transitions_map:
                transitions_map[key] = VersionTransition(
                    from_version_id=r["from_version_id"],
                    to_version_id=r["to_version_id"],
                    from_version_number=str(r["from_version_number"] or "1"),
                    to_version_number=str(r["to_version_number"] or "2"),
                    effective_date=r["effective_date"],
                    changes_count=0,
                    changes=[],
                )

            detail = SectionChangeDetail(
                section_name=r["section_name"],
                change_type=r["change_type"],
                diff=r["diff"] or "",
                added_lines=int(r["added_lines"] or 0),
                removed_lines=int(r["removed_lines"] or 0),
                similarity_ratio=float(r["similarity_ratio"] or 0.0),
                summary=r["summary"],
            )
            transitions_map[key].changes.append(detail)
            transitions_map[key].changes_count += 1
            total_changes += 1

        timeline_list = list(transitions_map.values())

        return DrugChangesTimelineResponse(
            drug_name=normalized_name,
            spl_set_id=spl_set_id,
            total_versions=total_versions,
            total_transitions=len(timeline_list),
            total_changes=total_changes,
            timeline=timeline_list,
        )


_graph_service: GraphService | None = None


def get_graph_service(manager: Neo4jManager = Depends(get_neo4j_manager)) -> GraphService:
    """Dependency provider for GraphService."""
    global _graph_service
    if _graph_service is None or manager is not None:
        _graph_service = GraphService(manager=manager)
    return _graph_service
