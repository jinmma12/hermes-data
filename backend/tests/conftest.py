"""Shared pytest fixtures for Vessel backend tests.

Provides async database sessions, sample domain objects, a pre-loaded
plugin registry, and mock helpers for external dependencies (NiFi, HTTP).
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from vessel.domain.models.base import Base
from vessel.domain.models.definition import (
    AlgorithmDefinition,
    AlgorithmDefinitionVersion,
    CollectorDefinition,
    CollectorDefinitionVersion,
    TransferDefinition,
    TransferDefinitionVersion,
)
from vessel.domain.models.execution import (
    ExecutionEventLog,
    ExecutionSnapshot,
    ReprocessRequest,
    WorkItem,
    WorkItemExecution,
    WorkItemStepExecution,
)
from vessel.domain.models.instance import (
    AlgorithmInstance,
    AlgorithmInstanceVersion,
    CollectorInstance,
    CollectorInstanceVersion,
    TransferInstance,
    TransferInstanceVersion,
)
from vessel.domain.models.monitoring import PipelineActivation
from vessel.domain.models.pipeline import PipelineInstance, PipelineStep
from vessel.plugins.protocol import MessageType, VesselMessage
from vessel.plugins.registry import PluginManifest, PluginRegistry, PluginType


# ---------------------------------------------------------------------------
# Database fixtures (in-memory SQLite with aiosqlite)
# ---------------------------------------------------------------------------

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


def _remap_jsonb_to_json(metadata):
    """Replace JSONB columns with JSON for SQLite compatibility."""
    from sqlalchemy import JSON
    from sqlalchemy.dialects.postgresql import JSONB

    for table in metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, JSONB):
                column.type = JSON()


@pytest_asyncio.fixture
async def async_engine():
    """Create an in-memory async SQLite engine with all tables."""
    _remap_jsonb_to_json(Base.metadata)
    engine = create_async_engine(TEST_DB_URL, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def async_session(async_engine) -> AsyncGenerator[AsyncSession, None]:
    """Yield an async session bound to the in-memory SQLite engine."""
    session_factory = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def session_factory(async_engine) -> async_sessionmaker[AsyncSession]:
    """Return a session factory for services that need to create their own sessions."""
    return async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


# ---------------------------------------------------------------------------
# Definition fixtures
# ---------------------------------------------------------------------------

REST_API_INPUT_SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "required": ["url", "method", "interval_seconds"],
    "properties": {
        "url": {"type": "string", "format": "uri"},
        "method": {"type": "string", "enum": ["GET", "POST"], "default": "GET"},
        "interval_seconds": {
            "type": "integer",
            "minimum": 10,
            "maximum": 86400,
            "default": 300,
        },
        "timeout_seconds": {"type": "integer", "minimum": 1, "default": 30},
    },
}

REST_API_UI_SCHEMA: dict[str, Any] = {
    "ui:order": ["url", "method", "interval_seconds", "timeout_seconds"],
    "url": {"ui:placeholder": "https://api.example.com/v1/data"},
}

REST_API_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "status_code": {"type": "integer"},
        "data": {"type": ["array", "object"]},
        "record_count": {"type": "integer"},
    },
}


@pytest_asyncio.fixture
async def sample_collector_definition(async_session: AsyncSession):
    """Create a REST API collector definition with one published version."""
    defn = CollectorDefinition(
        id=uuid.UUID("a0000000-0000-0000-0000-000000000001"),
        code="rest-api-collector",
        name="REST API Collector",
        description="Collects data from a REST API endpoint.",
        category="Data Collection",
        status="ACTIVE",
    )
    async_session.add(defn)
    await async_session.flush()

    ver = CollectorDefinitionVersion(
        id=uuid.UUID("b0000000-0000-0000-0000-000000000001"),
        definition_id=defn.id,
        version_no=1,
        input_schema=REST_API_INPUT_SCHEMA,
        ui_schema=REST_API_UI_SCHEMA,
        output_schema=REST_API_OUTPUT_SCHEMA,
        default_config={"method": "GET", "interval_seconds": 300, "timeout_seconds": 30},
        execution_type="PLUGIN",
        execution_ref="COLLECTOR:rest-api-collector",
        is_published=True,
    )
    async_session.add(ver)
    await async_session.flush()
    return defn, ver


@pytest_asyncio.fixture
async def sample_algorithm_definition(async_session: AsyncSession):
    """Create a threshold-based algorithm definition with one published version."""
    defn = AlgorithmDefinition(
        id=uuid.UUID("a0000000-0000-0000-0000-000000000002"),
        code="threshold-algorithm",
        name="Threshold Filter",
        description="Filters data based on configurable thresholds.",
        category="Data Processing",
        status="ACTIVE",
    )
    async_session.add(defn)
    await async_session.flush()

    ver = AlgorithmDefinitionVersion(
        id=uuid.UUID("b0000000-0000-0000-0000-000000000002"),
        definition_id=defn.id,
        version_no=1,
        input_schema={
            "type": "object",
            "required": ["threshold"],
            "properties": {
                "threshold": {"type": "number", "minimum": 0},
                "field_name": {"type": "string", "default": "value"},
            },
        },
        output_schema={"type": "object", "properties": {"filtered_count": {"type": "integer"}}},
        default_config={"threshold": 2.5, "field_name": "value"},
        execution_type="PLUGIN",
        execution_ref="ALGORITHM:threshold-algorithm",
        is_published=True,
    )
    async_session.add(ver)
    await async_session.flush()
    return defn, ver


@pytest_asyncio.fixture
async def sample_transfer_definition(async_session: AsyncSession):
    """Create a file output transfer definition with one published version."""
    defn = TransferDefinition(
        id=uuid.UUID("a0000000-0000-0000-0000-000000000003"),
        code="file-output",
        name="File Output",
        description="Writes processed data to a file.",
        category="Data Transfer",
        status="ACTIVE",
    )
    async_session.add(defn)
    await async_session.flush()

    ver = TransferDefinitionVersion(
        id=uuid.UUID("b0000000-0000-0000-0000-000000000003"),
        definition_id=defn.id,
        version_no=1,
        input_schema={
            "type": "object",
            "required": ["output_path"],
            "properties": {
                "output_path": {"type": "string"},
                "format": {"type": "string", "enum": ["json", "csv"], "default": "json"},
            },
        },
        output_schema={"type": "object", "properties": {"bytes_written": {"type": "integer"}}},
        default_config={"output_path": "/tmp/vessel-output", "format": "json"},
        execution_type="PLUGIN",
        execution_ref="TRANSFER:file-output",
        is_published=True,
    )
    async_session.add(ver)
    await async_session.flush()
    return defn, ver


# ---------------------------------------------------------------------------
# Instance fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def sample_collector_instance(
    async_session: AsyncSession, sample_collector_definition
):
    """Create a collector instance with a current (published) recipe."""
    defn, def_ver = sample_collector_definition
    inst = CollectorInstance(
        definition_id=defn.id,
        name="My REST Collector",
        status="ACTIVE",
    )
    async_session.add(inst)
    await async_session.flush()

    ver = CollectorInstanceVersion(
        instance_id=inst.id,
        def_version_id=def_ver.id,
        version_no=1,
        config_json={
            "url": "https://api.example.com/data",
            "method": "GET",
            "interval_seconds": 60,
        },
        is_current=True,
        created_by="test-operator",
        change_note="Initial configuration",
    )
    async_session.add(ver)
    await async_session.flush()
    return inst, ver


@pytest_asyncio.fixture
async def sample_algorithm_instance(
    async_session: AsyncSession, sample_algorithm_definition
):
    """Create an algorithm instance with a current recipe."""
    defn, def_ver = sample_algorithm_definition
    inst = AlgorithmInstance(
        definition_id=defn.id,
        name="My Threshold Filter",
        status="ACTIVE",
    )
    async_session.add(inst)
    await async_session.flush()

    ver = AlgorithmInstanceVersion(
        instance_id=inst.id,
        def_version_id=def_ver.id,
        version_no=1,
        config_json={"threshold": 2.5, "field_name": "value"},
        is_current=True,
        created_by="test-operator",
        change_note="Initial threshold config",
    )
    async_session.add(ver)
    await async_session.flush()
    return inst, ver


@pytest_asyncio.fixture
async def sample_transfer_instance(
    async_session: AsyncSession, sample_transfer_definition
):
    """Create a transfer instance with a current recipe."""
    defn, def_ver = sample_transfer_definition
    inst = TransferInstance(
        definition_id=defn.id,
        name="My File Output",
        status="ACTIVE",
    )
    async_session.add(inst)
    await async_session.flush()

    ver = TransferInstanceVersion(
        instance_id=inst.id,
        def_version_id=def_ver.id,
        version_no=1,
        config_json={"output_path": "/tmp/output.json", "format": "json"},
        is_current=True,
        created_by="test-operator",
        change_note="Initial output config",
    )
    async_session.add(ver)
    await async_session.flush()
    return inst, ver


# ---------------------------------------------------------------------------
# Pipeline fixture
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def sample_pipeline(
    async_session: AsyncSession,
    sample_collector_instance,
    sample_algorithm_instance,
    sample_transfer_instance,
):
    """Create a 3-step pipeline: collect -> algorithm -> transfer."""
    coll_inst, _ = sample_collector_instance
    algo_inst, _ = sample_algorithm_instance
    xfer_inst, _ = sample_transfer_instance

    pipeline = PipelineInstance(
        name="Test Pipeline",
        description="A test pipeline with 3 steps.",
        monitoring_type="FILE_MONITOR",
        monitoring_config={
            "watch_path": "/tmp/vessel-watch",
            "pattern": "*.csv",
            "interval": 5,
        },
        status="ACTIVE",
    )
    async_session.add(pipeline)
    await async_session.flush()

    step1 = PipelineStep(
        pipeline_instance_id=pipeline.id,
        step_order=1,
        step_type="COLLECT",
        ref_type="COLLECTOR",
        ref_id=coll_inst.id,
        is_enabled=True,
        on_error="STOP",
    )
    step2 = PipelineStep(
        pipeline_instance_id=pipeline.id,
        step_order=2,
        step_type="ALGORITHM",
        ref_type="ALGORITHM",
        ref_id=algo_inst.id,
        is_enabled=True,
        on_error="STOP",
    )
    step3 = PipelineStep(
        pipeline_instance_id=pipeline.id,
        step_order=3,
        step_type="TRANSFER",
        ref_type="TRANSFER",
        ref_id=xfer_inst.id,
        is_enabled=True,
        on_error="STOP",
    )
    async_session.add_all([step1, step2, step3])
    await async_session.flush()

    return pipeline, [step1, step2, step3]


# ---------------------------------------------------------------------------
# Work item fixture
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def sample_work_item(async_session: AsyncSession, sample_pipeline):
    """Create a work item in DETECTED status linked to the sample pipeline."""
    pipeline, steps = sample_pipeline

    activation = PipelineActivation(
        pipeline_instance_id=pipeline.id,
        status="RUNNING",
    )
    async_session.add(activation)
    await async_session.flush()

    work_item = WorkItem(
        pipeline_activation_id=activation.id,
        pipeline_instance_id=pipeline.id,
        source_type="FILE",
        source_key="test-data-001.csv",
        source_metadata={"path": "/tmp/vessel-watch/test-data-001.csv", "size": 1024},
        dedup_key="FILE:abc123def456",
        status="DETECTED",
    )
    async_session.add(work_item)
    await async_session.flush()
    return work_item, activation


# ---------------------------------------------------------------------------
# Plugin registry fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def plugin_registry(tmp_path: Path) -> PluginRegistry:
    """Return a PluginRegistry pre-loaded with three sample plugin manifests."""
    registry = PluginRegistry()

    for ptype, name, desc in [
        ("COLLECTOR", "rest-api-collector", "REST API Collector"),
        ("ALGORITHM", "threshold-algorithm", "Threshold Filter"),
        ("TRANSFER", "file-output", "File Output"),
    ]:
        plugin_dir = tmp_path / name
        plugin_dir.mkdir()
        (plugin_dir / "main.py").write_text("# plugin entrypoint\n")

        manifest = PluginManifest(
            name=name,
            version="1.0.0",
            type=PluginType(ptype),
            description=desc,
            author="vessel-test",
            license="Apache-2.0",
            runtime="python3",
            entrypoint="main.py",
            input_schema={"type": "object", "properties": {}},
            output_schema={"type": "object", "properties": {}},
            plugin_dir=plugin_dir,
        )
        registry.register_plugin(manifest)

    return registry


# ---------------------------------------------------------------------------
# Mock NiFi client fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_nifi_client():
    """Return an httpx-compatible mock for NiFi API calls."""
    mock = AsyncMock()
    mock.get = AsyncMock()
    mock.put = AsyncMock()
    mock.post = AsyncMock()
    mock.delete = AsyncMock()

    # Default success responses
    ok_response = MagicMock()
    ok_response.status_code = 200
    ok_response.json.return_value = {"status": "ok"}
    ok_response.raise_for_status = MagicMock()

    mock.get.return_value = ok_response
    mock.put.return_value = ok_response
    mock.post.return_value = ok_response

    return mock


# ---------------------------------------------------------------------------
# Helper factory fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def make_vessel_message():
    """Factory for creating VesselMessage instances."""

    def _make(msg_type: str, **data: Any) -> VesselMessage:
        return VesselMessage(type=MessageType(msg_type), data=data)

    return _make


@pytest.fixture
def make_manifest(tmp_path: Path):
    """Factory for creating PluginManifest instances on disk."""

    def _make(
        name: str = "test-plugin",
        plugin_type: str = "COLLECTOR",
        version: str = "1.0.0",
        runtime: str = "python3",
        entrypoint: str = "main.py",
        input_schema: dict | None = None,
    ) -> tuple[PluginManifest, Path]:
        plugin_dir = tmp_path / name
        plugin_dir.mkdir(exist_ok=True)
        (plugin_dir / entrypoint).write_text("# entrypoint\n")

        manifest_data = {
            "name": name,
            "version": version,
            "type": plugin_type,
            "description": f"Test {name} plugin",
            "author": "test",
            "license": "MIT",
            "runtime": runtime,
            "entrypoint": entrypoint,
            "inputSchema": input_schema or {"type": "object"},
        }
        (plugin_dir / "vessel-plugin.json").write_text(
            json.dumps(manifest_data, indent=2)
        )

        manifest = PluginManifest.from_dict(manifest_data, plugin_dir)
        return manifest, plugin_dir

    return _make
