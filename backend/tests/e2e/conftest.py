"""E2E test fixtures.

Reuses the root conftest's in-memory SQLite engine and session fixtures.
Adds service-layer fixtures for higher-level E2E operator flows.

Design decisions:
- FakeDispatcher replaces real plugin/HTTP dispatch with deterministic returns.
- All orchestrator calls are wrapped in asyncio.wait_for() at the test level
  to prevent hanging if event loop management differs across pytest-asyncio versions.
- Step types use the current Python backend naming (ALGORITHM, TRANSFER) because
  the ORM models and PipelineManager._INSTANCE_MODELS map have not been renamed
  to PROCESS/EXPORT yet. See CLAUDE.md naming gap note.
"""

from __future__ import annotations

import uuid

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from vessel.domain.models.definition import (
    AlgorithmDefinition,
    AlgorithmDefinitionVersion,
    CollectorDefinition,
    CollectorDefinitionVersion,
    TransferDefinition,
    TransferDefinitionVersion,
)
from vessel.domain.models.instance import (
    AlgorithmInstance,
    AlgorithmInstanceVersion,
    CollectorInstance,
    CollectorInstanceVersion,
    TransferInstance,
    TransferInstanceVersion,
)
from vessel.domain.services.execution_dispatcher import ExecutionDispatcher, ExecutionResult
from vessel.domain.services.pipeline_manager import PipelineManager
from vessel.domain.services.processing_orchestrator import ProcessingOrchestrator
from vessel.domain.services.snapshot_resolver import SnapshotResolver

# Hard timeout for any single test to prevent event-loop hangs.
E2E_TIMEOUT_SECONDS = 10


class FakeDispatcher(ExecutionDispatcher):
    """Deterministic dispatcher that records calls and returns configurable results.

    By default all steps succeed. Set fail_steps to a set of step_types to
    make those steps raise RuntimeError.
    """

    def __init__(self, fail_steps: set[str] | None = None) -> None:
        super().__init__()
        self.calls: list[dict] = []
        self.fail_steps: set[str] = fail_steps or set()

    async def dispatch(self, execution_type, execution_ref, config, input_data, context):
        step_type = context.get("step_type", "")
        self.calls.append({
            "execution_type": execution_type,
            "execution_ref": execution_ref,
            "config": config,
            "step_type": step_type,
        })
        if step_type in self.fail_steps:
            raise RuntimeError(f"Simulated {step_type} failure")
        return ExecutionResult(
            success=True,
            output={"result": f"{step_type}_output"},
            summary={"status": "ok", "step_type": step_type},
            duration_ms=10,
            logs=[],
        )


@pytest_asyncio.fixture
async def e2e_definitions(async_session: AsyncSession):
    """Seed a complete set of definitions: collector, processor, exporter.

    NOTE: Python backend ORM still uses AlgorithmDefinition / TransferDefinition.
    Frontend and .NET engine use PROCESS / EXPORT. This fixture uses the
    Python-layer naming to match what PipelineManager actually validates.
    """
    collector_def = CollectorDefinition(
        id=uuid.UUID("e0000000-0000-0000-0000-000000000001"),
        code="ftp-collector",
        name="FTP Collector",
        description="Collects files from FTP server",
        category="Data Collection",
        status="ACTIVE",
    )
    collector_def_ver = CollectorDefinitionVersion(
        id=uuid.UUID("e1000000-0000-0000-0000-000000000001"),
        definition_id=collector_def.id,
        version_no=1,
        input_schema={"type": "object", "properties": {"host": {"type": "string"}}},
        output_schema={"type": "object"},
        default_config={"host": "ftp.example.com", "port": 21},
        execution_type="PLUGIN",
        execution_ref="COLLECTOR:ftp-collector",
        is_published=True,
    )

    algo_def = AlgorithmDefinition(
        id=uuid.UUID("e0000000-0000-0000-0000-000000000002"),
        code="json-parser",
        name="JSON Parser",
        description="Parses JSON data",
        category="Data Processing",
        status="ACTIVE",
    )
    algo_def_ver = AlgorithmDefinitionVersion(
        id=uuid.UUID("e1000000-0000-0000-0000-000000000002"),
        definition_id=algo_def.id,
        version_no=1,
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        default_config={"format": "json"},
        execution_type="PLUGIN",
        execution_ref="ALGORITHM:json-parser",
        is_published=True,
    )

    transfer_def = TransferDefinition(
        id=uuid.UUID("e0000000-0000-0000-0000-000000000003"),
        code="db-writer",
        name="DB Writer",
        description="Writes data to database",
        category="Data Export",
        status="ACTIVE",
    )
    transfer_def_ver = TransferDefinitionVersion(
        id=uuid.UUID("e1000000-0000-0000-0000-000000000003"),
        definition_id=transfer_def.id,
        version_no=1,
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        default_config={"table": "output_data"},
        execution_type="PLUGIN",
        execution_ref="TRANSFER:db-writer",
        is_published=True,
    )

    async_session.add_all([
        collector_def, collector_def_ver,
        algo_def, algo_def_ver,
        transfer_def, transfer_def_ver,
    ])
    await async_session.flush()
    return {
        "collector": (collector_def, collector_def_ver),
        "processor": (algo_def, algo_def_ver),
        "exporter": (transfer_def, transfer_def_ver),
    }


@pytest_asyncio.fixture
async def e2e_instances(async_session: AsyncSession, e2e_definitions):
    """Seed instances for each definition with initial recipes."""
    coll_def, coll_ver = e2e_definitions["collector"]
    proc_def, proc_ver = e2e_definitions["processor"]
    exp_def, exp_ver = e2e_definitions["exporter"]

    coll_inst = CollectorInstance(definition_id=coll_def.id, name="FTP Source", status="ACTIVE")
    async_session.add(coll_inst)
    await async_session.flush()
    coll_inst_ver = CollectorInstanceVersion(
        instance_id=coll_inst.id, def_version_id=coll_ver.id, version_no=1,
        config_json={"host": "ftp.prod.com", "port": 21, "path": "/data"},
        is_current=True, created_by="operator", change_note="Initial config",
    )

    proc_inst = AlgorithmInstance(definition_id=proc_def.id, name="JSON Parser", status="ACTIVE")
    async_session.add(proc_inst)
    await async_session.flush()
    proc_inst_ver = AlgorithmInstanceVersion(
        instance_id=proc_inst.id, def_version_id=proc_ver.id, version_no=1,
        config_json={"format": "json", "encoding": "utf-8"},
        is_current=True, created_by="operator", change_note="Initial config",
    )

    exp_inst = TransferInstance(definition_id=exp_def.id, name="DB Writer", status="ACTIVE")
    async_session.add(exp_inst)
    await async_session.flush()
    exp_inst_ver = TransferInstanceVersion(
        instance_id=exp_inst.id, def_version_id=exp_ver.id, version_no=1,
        config_json={"table": "output_data", "batch_size": 100},
        is_current=True, created_by="operator", change_note="Initial config",
    )

    async_session.add_all([coll_inst_ver, proc_inst_ver, exp_inst_ver])
    await async_session.flush()

    return {
        "collector": (coll_inst, coll_inst_ver),
        "processor": (proc_inst, proc_inst_ver),
        "exporter": (exp_inst, exp_inst_ver),
    }


@pytest_asyncio.fixture
async def pipeline_manager(async_session: AsyncSession) -> PipelineManager:
    return PipelineManager(db=async_session)


@pytest_asyncio.fixture
async def fake_dispatcher() -> FakeDispatcher:
    return FakeDispatcher()


@pytest_asyncio.fixture
async def orchestrator(
    async_session: AsyncSession, fake_dispatcher: FakeDispatcher,
) -> ProcessingOrchestrator:
    return ProcessingOrchestrator(
        db=async_session,
        dispatcher=fake_dispatcher,
        snapshot_resolver=SnapshotResolver(async_session),
    )
