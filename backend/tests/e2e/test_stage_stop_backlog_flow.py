"""E2E: Stage stop → backlog accumulate → resume → drain flow.

Full operator scenario using the service layer:
1. Create and activate pipeline
2. Stop process stage
3. Collector produces work items
4. Verify backlog visible
5. Resume process stage
6. Process drains backlog
7. Verify empty queue
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from hermes.domain.models.execution import (
    WorkItem,
    WorkItemExecution,
    WorkItemStepExecution,
)
from hermes.domain.services.pipeline_manager import PipelineManager
from hermes.domain.services.stage_lifecycle import StageLifecycleManager

from .conftest import E2E_TIMEOUT_SECONDS


@pytest.mark.asyncio
async def test_full_stop_backlog_resume_drain_flow(
    async_session: AsyncSession,
    e2e_instances,
    pipeline_manager: PipelineManager,
):
    """P0 E2E: stop stage → backlog → resume → drain → empty queue."""
    coll_inst, _ = e2e_instances["collector"]
    proc_inst, _ = e2e_instances["processor"]
    exp_inst, _ = e2e_instances["exporter"]

    async def _run():
        # 1. Create and activate pipeline
        pipeline = await pipeline_manager.create_pipeline(
            name="Stage Lifecycle E2E",
            monitoring_type="FTP_MONITOR",
            monitoring_config={"host": "ftp.example.com"},
        )
        step1 = await pipeline_manager.add_step(
            pipeline.id, step_type="COLLECT", ref_type="COLLECTOR", ref_id=coll_inst.id,
        )
        step2 = await pipeline_manager.add_step(
            pipeline.id, step_type="ALGORITHM", ref_type="ALGORITHM", ref_id=proc_inst.id,
        )
        await pipeline_manager.add_step(
            pipeline.id, step_type="TRANSFER", ref_type="TRANSFER", ref_id=exp_inst.id,
        )
        activation = await pipeline_manager.activate_pipeline(pipeline.id)

        lifecycle = StageLifecycleManager(db=async_session)

        # 2. Stop process stage
        state = await lifecycle.stop_stage(activation.id, step2.id, stopped_by="admin")
        assert state.runtime_status == "STOPPED"

        # Activation must still be running
        await async_session.refresh(activation)
        assert activation.status in ("STARTING", "RUNNING")

        # 3. Simulate collector producing work items
        items: list[WorkItem] = []
        for i in range(4):
            wi = WorkItem(
                pipeline_activation_id=activation.id,
                pipeline_instance_id=pipeline.id,
                source_type="FILE",
                source_key=f"e2e-{i}.csv",
                dedup_key=f"FILE:e2e-{i}",
                status="DETECTED",
            )
            async_session.add(wi)
            items.append(wi)
        await async_session.flush()

        # Simulate collect step completion for all items
        exec_ids = []
        for wi in items:
            exec_record = WorkItemExecution(
                work_item_id=wi.id, execution_no=1,
                trigger_type="INITIAL", status="RUNNING",
            )
            async_session.add(exec_record)
            await async_session.flush()
            wi.execution_count = 1

            step_exec = WorkItemStepExecution(
                execution_id=exec_record.id,
                pipeline_step_id=step1.id,
                step_type="COLLECT", step_order=1,
                status="COMPLETED",
            )
            async_session.add(step_exec)
            exec_ids.append(exec_record.id)
        await async_session.flush()

        # 4. Verify backlog visible
        summaries = await lifecycle.get_queue_summary(activation.id)
        proc_summary = next(s for s in summaries if s.stage_order == step2.step_order)
        assert proc_summary.runtime_status == "STOPPED"
        assert proc_summary.queued_count >= 4, (
            f"Expected >=4 queued, got {proc_summary.queued_count}"
        )

        # 5. Resume process stage
        resumed = await lifecycle.resume_stage(activation.id, step2.id)
        assert resumed.runtime_status == "RUNNING"

        # 6. Simulate processing (mark step2 completed for all items)
        for wi, eid in zip(items, exec_ids):
            step_exec = WorkItemStepExecution(
                execution_id=eid,
                pipeline_step_id=step2.id,
                step_type="ALGORITHM", step_order=2,
                status="COMPLETED",
            )
            async_session.add(step_exec)
        await async_session.flush()

        # 7. Verify queue drained
        summaries = await lifecycle.get_queue_summary(activation.id)
        proc_summary = next(s for s in summaries if s.stage_order == step2.step_order)
        assert proc_summary.queued_count == 0, (
            f"Queue should be empty after drain, got {proc_summary.queued_count}"
        )
        assert proc_summary.completed_count >= 4

    await asyncio.wait_for(_run(), timeout=E2E_TIMEOUT_SECONDS)


@pytest.mark.asyncio
async def test_pipeline_deactivate_vs_stage_stop(
    async_session: AsyncSession,
    e2e_instances,
    pipeline_manager: PipelineManager,
):
    """Confirm deactivate and stage stop are distinct operations."""
    coll_inst, _ = e2e_instances["collector"]

    async def _run():
        pipeline = await pipeline_manager.create_pipeline(
            name="Deactivate vs Stop",
            monitoring_type="FILE_MONITOR",
        )
        step1 = await pipeline_manager.add_step(
            pipeline.id, step_type="COLLECT", ref_type="COLLECTOR", ref_id=coll_inst.id,
        )
        activation = await pipeline_manager.activate_pipeline(pipeline.id)

        lifecycle = StageLifecycleManager(db=async_session)

        # Stage stop: activation stays RUNNING
        await lifecycle.stop_stage(activation.id, step1.id)
        await async_session.refresh(activation)
        assert activation.status in ("STARTING", "RUNNING")

        # Resume stage
        await lifecycle.resume_stage(activation.id, step1.id)

        # Pipeline deactivate: activation goes STOPPED
        await pipeline_manager.deactivate_pipeline(pipeline.id)
        await async_session.refresh(activation)
        assert activation.status == "STOPPED"

    await asyncio.wait_for(_run(), timeout=E2E_TIMEOUT_SECONDS)
