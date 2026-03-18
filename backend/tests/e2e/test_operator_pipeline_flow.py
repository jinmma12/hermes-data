"""E2E: Operator pipeline flow — create, configure, activate, ingest, inspect.

Tests the P0 operator journey using the service layer directly with
in-memory SQLite. No FastAPI app bootstrap, no gRPC, no Docker.

All async operations are guarded by asyncio.wait_for() to prevent
hanging on event-loop misconfigurations across pytest-asyncio versions.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vessel.domain.models.execution import (
    ExecutionEventLog,
    WorkItem,
    WorkItemStepExecution,
)
from vessel.domain.services.pipeline_manager import PipelineManager
from vessel.domain.services.processing_orchestrator import ProcessingOrchestrator

from .conftest import E2E_TIMEOUT_SECONDS


@pytest.mark.asyncio
async def test_operator_can_create_activate_and_inspect_pipeline(
    async_session: AsyncSession,
    e2e_instances,
    pipeline_manager: PipelineManager,
):
    """P0 flow: create pipeline -> add steps -> validate -> activate -> inspect status."""
    coll_inst, _ = e2e_instances["collector"]
    proc_inst, _ = e2e_instances["processor"]
    exp_inst, _ = e2e_instances["exporter"]

    async def _run():
        # 1. Create pipeline
        pipeline = await pipeline_manager.create_pipeline(
            name="FTP -> JSON Parse -> DB Writer",
            monitoring_type="FTP_MONITOR",
            monitoring_config={"host": "ftp.prod.com", "path": "/data", "interval": 60},
            description="Production FTP ingestion pipeline",
        )
        assert pipeline.status == "DRAFT"

        # 2. Add steps: collect -> process -> export
        step1 = await pipeline_manager.add_step(
            pipeline.id, step_type="COLLECT", ref_type="COLLECTOR", ref_id=coll_inst.id,
        )
        step2 = await pipeline_manager.add_step(
            pipeline.id, step_type="ALGORITHM", ref_type="ALGORITHM", ref_id=proc_inst.id,
        )
        step3 = await pipeline_manager.add_step(
            pipeline.id, step_type="TRANSFER", ref_type="TRANSFER", ref_id=exp_inst.id,
        )
        assert step1.step_order == 1
        assert step2.step_order == 2
        assert step3.step_order == 3

        # 3. Validate
        validation = await pipeline_manager.validate_pipeline(pipeline.id)
        assert validation.valid, f"Validation failed: {[i.message for i in validation.issues]}"

        # 4. Activate
        activation = await pipeline_manager.activate_pipeline(pipeline.id, worker_id="worker-1")
        assert activation.status == "STARTING"
        assert activation.worker_id == "worker-1"

        # 5. Inspect status
        status = await pipeline_manager.get_pipeline_status(pipeline.id)
        assert status.status == "ACTIVE"
        assert status.step_count == 3
        assert status.active_activation_id == activation.id
        assert status.activation_status == "STARTING"

    await asyncio.wait_for(_run(), timeout=E2E_TIMEOUT_SECONDS)


@pytest.mark.asyncio
async def test_operator_dashboard_reflects_work_item_counts_and_completion(
    async_session: AsyncSession,
    e2e_instances,
    pipeline_manager: PipelineManager,
    orchestrator: ProcessingOrchestrator,
    fake_dispatcher,
):
    """P0 flow: seed work items -> process -> verify dashboard counts."""
    coll_inst, _ = e2e_instances["collector"]
    proc_inst, _ = e2e_instances["processor"]
    exp_inst, _ = e2e_instances["exporter"]

    async def _run():
        # Setup pipeline
        pipeline = await pipeline_manager.create_pipeline(
            name="Dashboard Test Pipeline",
            monitoring_type="FTP_MONITOR",
            monitoring_config={"host": "ftp.example.com"},
        )
        await pipeline_manager.add_step(
            pipeline.id, step_type="COLLECT", ref_type="COLLECTOR", ref_id=coll_inst.id,
        )
        await pipeline_manager.add_step(
            pipeline.id, step_type="ALGORITHM", ref_type="ALGORITHM", ref_id=proc_inst.id,
        )
        await pipeline_manager.add_step(
            pipeline.id, step_type="TRANSFER", ref_type="TRANSFER", ref_id=exp_inst.id,
        )
        activation = await pipeline_manager.activate_pipeline(pipeline.id)

        # Simulate file detection -> create work items
        work_items = []
        for i in range(3):
            wi = WorkItem(
                pipeline_activation_id=activation.id,
                pipeline_instance_id=pipeline.id,
                source_type="FILE",
                source_key=f"data-{i:03d}.csv",
                source_metadata={"path": f"/data/data-{i:03d}.csv", "size": 1024 * (i + 1)},
                dedup_key=f"FILE:hash-{i:03d}",
                status="DETECTED",
            )
            async_session.add(wi)
            work_items.append(wi)
        await async_session.flush()

        # Process first work item through all 3 steps
        execution = await orchestrator.process_work_item(work_items[0].id)

        assert execution.status == "COMPLETED"
        assert execution.execution_no == 1

        # Verify dispatcher was called 3 times (collect, process, export)
        assert len(fake_dispatcher.calls) == 3
        assert fake_dispatcher.calls[0]["step_type"] == "COLLECT"
        assert fake_dispatcher.calls[1]["step_type"] == "ALGORITHM"
        assert fake_dispatcher.calls[2]["step_type"] == "TRANSFER"

        # Verify work item status
        await async_session.refresh(work_items[0])
        assert work_items[0].status == "COMPLETED"
        assert work_items[0].last_completed_at is not None

        # Verify step executions exist
        stmt = (
            select(WorkItemStepExecution)
            .where(WorkItemStepExecution.execution_id == execution.id)
            .order_by(WorkItemStepExecution.step_order)
        )
        result = await async_session.execute(stmt)
        step_execs = result.scalars().all()
        assert len(step_execs) == 3
        assert all(se.status == "COMPLETED" for se in step_execs)

        # Verify event log has entries
        stmt = select(ExecutionEventLog).where(
            ExecutionEventLog.execution_id == execution.id,
        )
        result = await async_session.execute(stmt)
        events = result.scalars().all()
        event_codes = [e.event_code for e in events]
        assert "EXECUTION_START" in event_codes
        assert "COLLECT_START" in event_codes
        assert "COLLECT_DONE" in event_codes
        assert "EXECUTION_END" in event_codes

        # Dashboard: pipeline status should show 3 work items
        status = await pipeline_manager.get_pipeline_status(pipeline.id)
        assert status.work_item_count == 3
        assert status.status == "ACTIVE"

    await asyncio.wait_for(_run(), timeout=E2E_TIMEOUT_SECONDS)


@pytest.mark.asyncio
async def test_pipeline_validation_blocks_invalid_activation(
    async_session: AsyncSession,
    pipeline_manager: PipelineManager,
):
    """Operator cannot activate a pipeline with missing step references."""

    async def _run():
        pipeline = await pipeline_manager.create_pipeline(
            name="Invalid Pipeline",
            monitoring_type="FILE_MONITOR",
        )
        # Add step with nonexistent instance
        await pipeline_manager.add_step(
            pipeline.id,
            step_type="COLLECT",
            ref_type="COLLECTOR",
            ref_id=uuid.uuid4(),
        )

        validation = await pipeline_manager.validate_pipeline(pipeline.id)
        assert not validation.valid
        assert any("not found" in i.message for i in validation.issues)

        # Activation should fail
        with pytest.raises(ValueError, match="validation failed"):
            await pipeline_manager.activate_pipeline(pipeline.id)

    await asyncio.wait_for(_run(), timeout=E2E_TIMEOUT_SECONDS)
