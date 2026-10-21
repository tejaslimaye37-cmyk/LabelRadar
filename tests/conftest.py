"""Global test configuration and fixtures with mocked external services."""

from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.llm import LLMService
from app.db.neo4j import Neo4jManager
from app.db.postgres import PostgresManager
from app.main import create_application
from app.models.openfda import OpenFDALabelRecord
from app.services.graph_service import GraphService
from app.services.ingestion_service import IngestionService
from app.services.openfda_client import OpenFDAClient
from tests.fixtures.openfda_responses import LIPITOR_V1_RAW, LIPITOR_V2_RAW, LIPITOR_V3_RAW


@pytest.fixture
def test_settings() -> Settings:
    """Provides isolated test settings."""
    return Settings(
        APP_NAME="LabelRadar-Test",
        APP_ENV="testing",
        DEBUG=True,
        OPENAI_BASE_URL="http://mock-llm-server:11434/v1",
        OPENAI_API_KEY="mock-test-key",
        LLM_MODEL="qwen-test",
        NEO4J_URI="bolt://localhost:7687",
        NEO4J_USER="neo4j",
        NEO4J_PASSWORD="test_password",
        DATABASE_URL="sqlite+aiosqlite:///:memory:",
        POSTGRES_HOST="localhost",
        POSTGRES_PORT=5432,
        POSTGRES_USER="test_user",
        POSTGRES_PASSWORD="test_password",
        POSTGRES_DB="test_db",
    )


@pytest.fixture
def mock_openfda_records() -> list[OpenFDALabelRecord]:
    """Provides parsed realistic OpenFDALabelRecord instances."""
    return [
        OpenFDALabelRecord.model_validate(LIPITOR_V1_RAW),
        OpenFDALabelRecord.model_validate(LIPITOR_V2_RAW),
        OpenFDALabelRecord.model_validate(LIPITOR_V3_RAW),
    ]


@pytest.fixture
def mock_openfda_client(mock_openfda_records: list[OpenFDALabelRecord]) -> OpenFDAClient:
    """Mock OpenFDAClient returning pre-loaded historical records."""
    client = MagicMock(spec=OpenFDAClient)
    client.fetch_labels_for_drug = AsyncMock(return_value=mock_openfda_records)
    return client


class InMemoryGraphStore:
    """In-memory simulation of Neo4j graph for isolated integration testing."""

    def __init__(self):
        self.drugs: dict[str, dict[str, Any]] = {}
        self.versions: dict[str, dict[str, Any]] = {}
        self.sections: dict[str, dict[str, Any]] = {}
        self.edges: list[dict[str, Any]] = []

    def clear(self):
        self.drugs.clear()
        self.versions.clear()
        self.sections.clear()
        self.edges.clear()


@pytest.fixture
def memory_graph() -> InMemoryGraphStore:
    return InMemoryGraphStore()


@pytest.fixture
def mock_graph_service(memory_graph: InMemoryGraphStore) -> GraphService:
    """Mocked GraphService backed by an in-memory graph store."""
    service = MagicMock(spec=GraphService)

    async def _upsert_drug(drug):
        memory_graph.drugs[drug.name] = drug.model_dump()

    async def _upsert_version(drug_name, version):
        memory_graph.versions[version.version_id] = {
            "drug_name": drug_name,
            **version.model_dump(),
        }

    async def _upsert_section(version_id, section):
        memory_graph.sections[section.section_id] = {
            "version_id": version_id,
            **section.model_dump(),
        }

    async def _link_section_change(from_sec_id, to_sec_id, edge):
        memory_graph.edges.append({
            "from_section_id": from_sec_id,
            "to_section_id": to_sec_id,
            **edge.model_dump(),
        })

    async def _get_drug_change_timeline(drug_name, section_name=None, change_type=None):
        from app.models.schemas import (
            DrugChangesTimelineResponse,
            SectionChangeDetail,
            VersionTransition,
        )

        transitions_map: dict[tuple[str, str], VersionTransition] = {}
        total_changes = 0

        for edge in memory_graph.edges:
            if section_name and edge.get("section_name") != section_name:
                continue
            if change_type and edge.get("change_type") != change_type:
                continue

            from_sec_id = edge["from_section_id"]
            to_sec_id = edge["to_section_id"]
            from_vid = memory_graph.sections[from_sec_id]["version_id"]
            to_vid = memory_graph.sections[to_sec_id]["version_id"]
            v2_meta = memory_graph.versions.get(to_vid, {})
            v1_meta = memory_graph.versions.get(from_vid, {})

            key = (from_vid, to_vid)
            if key not in transitions_map:
                transitions_map[key] = VersionTransition(
                    from_version_id=from_vid,
                    to_version_id=to_vid,
                    from_version_number=str(v1_meta.get("version_number", "1")),
                    to_version_number=str(v2_meta.get("version_number", "2")),
                    effective_date=v2_meta.get("effective_date"),
                    changes_count=0,
                    changes=[],
                )

            detail = SectionChangeDetail(
                section_name=edge["section_name"],
                change_type=edge["change_type"],
                diff=edge["diff"],
                added_lines=edge["added_lines"],
                removed_lines=edge["removed_lines"],
                similarity_ratio=edge["similarity_ratio"],
                summary=edge.get("summary"),
            )
            transitions_map[key].changes.append(detail)
            transitions_map[key].changes_count += 1
            total_changes += 1

        timeline = list(transitions_map.values())
        return DrugChangesTimelineResponse(
            drug_name=drug_name.upper(),
            spl_set_id="spl-set-lipitor-001",
            total_versions=len(memory_graph.versions),
            total_transitions=len(timeline),
            total_changes=total_changes,
            timeline=timeline,
        )

    service.upsert_drug = AsyncMock(side_effect=_upsert_drug)
    service.upsert_version = AsyncMock(side_effect=_upsert_version)
    service.upsert_section = AsyncMock(side_effect=_upsert_section)
    service.link_section_change = AsyncMock(side_effect=_link_section_change)
    service.get_drug_change_timeline = AsyncMock(side_effect=_get_drug_change_timeline)
    return service


@pytest.fixture
def mock_postgres_manager() -> PostgresManager:
    """Mock PostgresManager providing mock async session."""
    manager = MagicMock(spec=PostgresManager)
    manager.check_health = AsyncMock(return_value=True)
    manager.init_db = AsyncMock()
    manager.close = AsyncMock()

    from contextlib import asynccontextmanager

    # Mock session
    mock_session = AsyncMock(spec=AsyncSession)
    mock_exec_result = MagicMock()
    mock_exec_result.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=mock_exec_result)
    mock_session.flush = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()
    mock_session.add = MagicMock()

    @asynccontextmanager
    async def _get_session():
        yield mock_session

    manager.get_session = _get_session
    return manager


@pytest.fixture
def mock_llm_service(test_settings: Settings) -> LLMService:
    """Mock LLMService simulating local or OpenAI model completion."""
    service = MagicMock(spec=LLMService)
    service.settings = test_settings
    service.model = test_settings.LLM_MODEL
    service.complete = AsyncMock(
        return_value="Mocked LLM summary: Boxed warning added for IMNM risk in Lipitor."
    )
    return service


@pytest.fixture
async def app_client(
    test_settings: Settings,
    mock_openfda_client: OpenFDAClient,
    mock_graph_service: GraphService,
    mock_postgres_manager: PostgresManager,
    mock_llm_service: LLMService,
) -> AsyncGenerator[AsyncClient, None]:
    """Test AsyncClient configured with mock services and overrides."""
    from app.core.llm import get_llm_service
    from app.db.neo4j import get_neo4j_manager
    from app.db.postgres import get_postgres_manager
    from app.services.graph_service import get_graph_service
    from app.services.ingestion_service import get_ingestion_service
    from app.services.openfda_client import get_openfda_client

    test_ingestion = IngestionService(
        openfda_client=mock_openfda_client,
        graph_service=mock_graph_service,
        postgres_manager=mock_postgres_manager,
    )

    mock_neo4j_manager = MagicMock(spec=Neo4jManager)
    mock_neo4j_manager.verify_connectivity = AsyncMock(return_value=True)
    mock_neo4j_manager.init_schema = AsyncMock()
    mock_neo4j_manager.close = AsyncMock()

    application = create_application()
    application.dependency_overrides[get_settings] = lambda: test_settings
    application.dependency_overrides[get_openfda_client] = lambda: mock_openfda_client
    application.dependency_overrides[get_graph_service] = lambda: mock_graph_service
    application.dependency_overrides[get_postgres_manager] = lambda: mock_postgres_manager
    application.dependency_overrides[get_neo4j_manager] = lambda: mock_neo4j_manager
    application.dependency_overrides[get_llm_service] = lambda: mock_llm_service
    application.dependency_overrides[get_ingestion_service] = lambda: test_ingestion

    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
