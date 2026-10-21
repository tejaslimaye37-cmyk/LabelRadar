"""Unit tests for Neo4j GraphService."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.db.neo4j import Neo4jManager
from app.models.graph import ChangedToEdge, ChangeType, DrugNode, LabelVersionNode, SectionNode
from app.services.graph_service import GraphService


@pytest.mark.asyncio
async def test_upsert_drug():
    mock_manager = MagicMock(spec=Neo4jManager)
    mock_session = AsyncMock()
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _session():
        yield mock_session

    mock_manager.get_session = _session

    service = GraphService(manager=mock_manager)
    drug = DrugNode(
        name="LIPITOR",
        brand_name="LIPITOR",
        generic_name="ATORVASTATIN CALCIUM",
        spl_set_id="spl-set-001",
    )
    await service.upsert_drug(drug)

    mock_session.run.assert_awaited_once()
    call_args = mock_session.run.await_args
    assert "MERGE (d:Drug {name: $name})" in call_args.args[0]
    assert call_args.kwargs["name"] == "LIPITOR"


@pytest.mark.asyncio
async def test_upsert_version_and_section():
    mock_manager = MagicMock(spec=Neo4jManager)
    mock_session = AsyncMock()
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _session():
        yield mock_session

    mock_manager.get_session = _session

    service = GraphService(manager=mock_manager)

    v_node = LabelVersionNode(
        version_id="v1",
        version_number="1",
        effective_date="2021-01-15",
    )
    await service.upsert_version("LIPITOR", v_node)
    assert "MERGE (d)-[:HAS_VERSION]->(v)" in mock_session.run.await_args.args[0]

    sec_node = SectionNode(
        section_id="v1:boxed_warning",
        section_name="boxed_warning",
        version_id="v1",
        text="Sample warning text",
        char_count=19,
    )
    await service.upsert_section("v1", sec_node)
    assert "MERGE (v)-[:HAS_SECTION]->(s)" in mock_session.run.await_args.args[0]


@pytest.mark.asyncio
async def test_link_section_change():
    mock_manager = MagicMock(spec=Neo4jManager)
    mock_session = AsyncMock()
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _session():
        yield mock_session

    mock_manager.get_session = _session

    service = GraphService(manager=mock_manager)
    edge = ChangedToEdge(
        change_type=ChangeType.MODIFIED,
        section_name="warnings_and_precautions",
        diff="--- v1\n+++ v2\n+Added line",
        added_lines=1,
        removed_lines=0,
        similarity_ratio=0.85,
        summary="Added IMNM warning",
    )
    await service.link_section_change("v1:warnings", "v2:warnings", edge)

    call_args = mock_session.run.await_args
    assert "MERGE (s1)-[r:CHANGED_TO]->(s2)" in call_args.args[0]
    assert call_args.kwargs["change_type"] == "modified"
    assert call_args.kwargs["similarity_ratio"] == 0.85


@pytest.mark.asyncio
async def test_get_drug_change_timeline_cypher_flow():
    mock_manager = MagicMock(spec=Neo4jManager)
    mock_session = AsyncMock()

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _session():
        yield mock_session

    mock_manager.get_session = _session

    # Mock count record
    mock_count_record = MagicMock()
    mock_count_record.__getitem__.side_effect = lambda key: 3 if key == "total_versions" else "spl-set-001"
    mock_count_res = AsyncMock()
    mock_count_res.single = AsyncMock(return_value=mock_count_record)

    # Mock timeline query stream
    class MockTimelineRecord:
        def __init__(self, data_dict):
            self._data = data_dict

        def data(self):
            return self._data

    timeline_data = [
        {
            "from_version_id": "v1",
            "from_version_number": "1",
            "to_version_id": "v2",
            "to_version_number": "2",
            "effective_date": "2022-06-10",
            "section_name": "boxed_warning",
            "change_type": "added",
            "diff": "+Added boxed warning",
            "added_lines": 5,
            "removed_lines": 0,
            "similarity_ratio": 0.0,
            "summary": "Added boxed warning",
        }
    ]

    async def mock_record_gen():
        for item in timeline_data:
            yield MockTimelineRecord(item)

    mock_timeline_res = mock_record_gen()

    async def mock_run(query, **kwargs):
        if "count(v)" in query:
            return mock_count_res
        return mock_timeline_res

    mock_session.run = AsyncMock(side_effect=mock_run)

    service = GraphService(manager=mock_manager)
    timeline = await service.get_drug_change_timeline("LIPITOR")

    assert timeline.drug_name == "LIPITOR"
    assert timeline.total_versions == 3
    assert timeline.total_transitions == 1
    assert timeline.total_changes == 1
    assert len(timeline.timeline) == 1
    trans = timeline.timeline[0]
    assert trans.from_version_id == "v1"
    assert trans.to_version_id == "v2"
    assert trans.changes[0].section_name == "boxed_warning"
    assert trans.changes[0].change_type == ChangeType.ADDED

