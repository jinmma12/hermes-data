"""API contract tests for stage runtime stop/resume and queue summary.

These test the service layer contracts that the API endpoints expose,
using the same in-memory SQLite session as other tests.
They do NOT spin up FastAPI — they test the business logic directly.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from hermes.domain.models.execution import (
    WorkItem,
    WorkItemExecution,
    WorkItemStepExecution,
)
from hermes.domain.services.pipeline_manager import PipelineManager
from hermes.domain.services.stage_lifecycle import StageLifecycleManager

TIMEOUT = 10


@pytest.mark.asyncio
async def test_stop_stage_returns_stopped_state(
    async_session: AsyncSession,
    sample_pipeline,
):
    """POST .../stages/{id}/stop → runtime_status=STOPPED."""

    async def _run():
        pipeline, steps = sample_pipeline
        mgr = PipelineManager(db=async_session)
        activation = await mgr.activate_pipeline(pipeline.id)

        lifecycle = StageLifecycleManager(db=async_session)
        process_step = sorted(steps, key=lambda s: s.step_order)[1]

        state = await lifecycle.stop_stage(activation.id, process_step.id, stopped_by="admin")
        assert state.runtime_status == "STOPPED"
        assert state.stopped_by == "admin"
        assert state.pipeline_activation_id == activation.id
        assert state.pipeline_step_id == process_step.id

    await asyncio.wait_for(_run(), timeout=TIMEOUT)


@pytest.mark.asyncio
async def test_resume_stage_returns_running_state(
    async_session: AsyncSession,
    sample_pipeline,
):
    """POST .../stages/{id}/resume → runtime_status=RUNNING."""

    async def _run():
        pipeline, steps = sample_pipeline
        mgr = PipelineManager(db=async_session)
        activation = await mgr.activate_pipeline(pipeline.id)

        lifecycle = StageLifecycleManager(db=async_session)
        process_step = sorted(steps, key=lambda s: s.step_order)[1]

        await lifecycle.stop_stage(activation.id, process_step.id)
        state = await lifecycle.resume_stage(activation.id, process_step.id)
        assert state.runtime_status == "RUNNING"
        assert state.resumed_at is not None

    await asyncio.wait_for(_run(), timeout=TIMEOUT)


@pytest.mark.asyncio
async def test_stop_invalid_stage_raises_error(
    async_session: AsyncSession,
    sample_pipeline,
):
    """Stop with a nonexistent step → ValueError."""

    async def _run():
        pipeline, steps = sample_pipeline
        mgr = PipelineManager(db=async_session)
        activation = await mgr.activate_pipeline(pipeline.id)

        lifecycle = StageLifecycleManager(db=async_session)
        with pytest.raises(ValueError, match="not found"):
            await lifecycle.stop_stage(activation.id, uuid.uuid4())

    await asyncio.wait_for(_run(), timeout=TIMEOUT)


@pytest.mark.asyncio
async def test_stop_invalid_activation_raises_error(
    async_session: AsyncSession,
    sample_pipeline,
):
    """Stop with a nonexistent activation → ValueError."""

    async def _run():
        _, steps = sample_pipeline
        lifecycle = StageLifecycleManager(db=async_session)
        with pytest.raises(ValueError, match="not found"):
            await lifecycle.stop_stage(uuid.uuid4(), steps[0].id)

    await asyncio.wait_for(_run(), timeout=TIMEOUT)


@pytest.mark.asyncio
async def test_queue_summary_returns_per_stage_counts(
    async_session: AsyncSession,
    sample_pipeline,
):
    """GET .../queues → list of StageQueueSummary with runtime_status + counts."""

    async def _run():
        pipeline, steps = sample_pipeline
        sorted_steps = sorted(steps, key=lambda s: s.step_order)
        collect_step = sorted_steps[0]

        mgr = PipelineManager(db=async_session)
        activation = await mgr.activate_pipeline(pipeline.id)

        # Create work items and complete collect step
        for i in range(3):
            wi = WorkItem(
                pipeline_activation_id=activation.id,
                pipeline_instance_id=pipeline.id,
                source_type="FILE",
                source_key=f"api-test-{i}.csv",
                dedup_key=f"FILE:api-test-{i}",
                status="DETECTED",
            )
            async_session.add(wi)
            await async_session.flush()

            exec_rec = WorkItemExecution(
                work_item_id=wi.id, execution_no=1,
                trigger_type="INITIAL", status="RUNNING",
            )
            async_session.add(exec_rec)
            await async_session.flush()
            wi.execution_count = 1

            step_exec = WorkItemStepExecution(
                execution_id=exec_rec.id,
                pipeline_step_id=collect_step.id,
                step_type=collect_step.step_type,
                step_order=collect_step.step_order,
                status="COMPLETED",
            )
            async_session.add(step_exec)
        await async_session.flush()

        lifecycle = StageLifecycleManager(db=async_session)
        summaries = await lifecycle.get_queue_summary(activation.id)

        # Should have summaries for all enabled steps
        assert len(summaries) >= 2

        # Collect step: 3 completed
        collect_summary = next(s for s in summaries if s.stage_order == collect_step.step_order)
        assert collect_summary.completed_count == 3
        assert collect_summary.runtime_status == "RUNNING"

        # Process step: 3 queued (waiting after collect)
        process_summary = next(s for s in summaries if s.stage_order == sorted_steps[1].step_order)
        assert process_summary.queued_count >= 3

    await asyncio.wait_for(_run(), timeout=TIMEOUT)


@pytest.mark.asyncio
async def test_pipeline_deactivate_is_separate_from_stage_stop(
    async_session: AsyncSession,
    sample_pipeline,
):
    """deactivate_pipeline != stop_stage — they affect different levels."""

    async def _run():
        pipeline, steps = sample_pipeline
        mgr = PipelineManager(db=async_session)
        activation = await mgr.activate_pipeline(pipeline.id)

        lifecycle = StageLifecycleManager(db=async_session)
        process_step = sorted(steps, key=lambda s: s.step_order)[1]

        # Stage stop: activation stays alive
        await lifecycle.stop_stage(activation.id, process_step.id)
        await async_session.refresh(activation)
        assert activation.status in ("STARTING", "RUNNING")

        # Pipeline deactivate: whole activation stops
        await lifecycle.resume_stage(activation.id, process_step.id)
        await mgr.deactivate_pipeline(pipeline.id)
        await async_session.refresh(activation)
        assert activation.status == "STOPPED"

    await asyncio.wait_for(_run(), timeout=TIMEOUT)
