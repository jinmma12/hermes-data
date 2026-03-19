"""Tests for stage queue visibility: backlog accumulation and drain.

Validates queue semantics from STAGE_LIFECYCLE_AND_QUEUE_MODEL.md:
- stopped process stage accumulates backlog (queued items before it)
- resumed process stage drains backlog
- export stopped causes backlog before export
- queue summary reflects empty state after drain
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
from hermes.domain.models.monitoring import PipelineActivation
from hermes.domain.services.pipeline_manager import PipelineManager
from hermes.domain.services.stage_lifecycle import StageLifecycleManager

TIMEOUT = 10


async def _create_work_items(
    session: AsyncSession,
    activation: PipelineActivation,
    pipeline_id,
    count: int = 3,
) -> list[WorkItem]:
    """Create DETECTED work items for testing."""
    items = []
    for i in range(count):
        wi = WorkItem(
            pipeline_activation_id=activation.id,
            pipeline_instance_id=pipeline_id,
            source_type="FILE",
            source_key=f"test-{i}.csv",
            dedup_key=f"FILE:test-{i}",
            status="DETECTED",
        )
        session.add(wi)
        items.append(wi)
    await session.flush()
    return items


async def _mark_step_completed(
    session: AsyncSession,
    work_item: WorkItem,
    step,
    execution_id=None,
):
    """Simulate a step execution completing for a work item."""
    if execution_id is None:
        exec_record = WorkItemExecution(
            work_item_id=work_item.id,
            execution_no=work_item.execution_count + 1,
            trigger_type="INITIAL",
            status="RUNNING",
        )
        session.add(exec_record)
        await session.flush()
        work_item.execution_count += 1
        execution_id = exec_record.id

    step_exec = WorkItemStepExecution(
        execution_id=execution_id,
        pipeline_step_id=step.id,
        step_type=step.step_type,
        step_order=step.step_order,
        status="COMPLETED",
    )
    session.add(step_exec)
    await session.flush()
    return execution_id


@pytest.mark.asyncio
async def test_stopped_process_stage_accumulates_backlog(
    async_session: AsyncSession,
    sample_pipeline,
):
    """Scenario 3: collect continues, process stopped → queued count increases."""

    async def _run():
        pipeline, steps = sample_pipeline
        sorted_steps = sorted(steps, key=lambda s: s.step_order)
        collect_step, process_step, export_step = sorted_steps[0], sorted_steps[1], sorted_steps[2]

        mgr = PipelineManager(db=async_session)
        activation = await mgr.activate_pipeline(pipeline.id)

        lifecycle = StageLifecycleManager(db=async_session)

        # Stop process stage
        await lifecycle.stop_stage(activation.id, process_step.id)

        # Simulate collector producing work items
        items = await _create_work_items(async_session, activation, pipeline.id, count=5)

        # Mark collect step as completed for all items
        for wi in items:
            await _mark_step_completed(async_session, wi, collect_step)

        # Check queue summary
        summaries = await lifecycle.get_queue_summary(activation.id)
        summary_by_order = {s.stage_order: s for s in summaries}

        # Process stage should show queued items
        process_summary = summary_by_order.get(process_step.step_order)
        assert process_summary is not None
        assert process_summary.runtime_status == "STOPPED"
        assert process_summary.queued_count >= 5, (
            f"Expected >=5 queued before process, got {process_summary.queued_count}"
        )

        # Export stage should show 0 queued (nothing passed process yet)
        export_summary = summary_by_order.get(export_step.step_order)
        assert export_summary is not None
        assert export_summary.queued_count == 0

    await asyncio.wait_for(_run(), timeout=TIMEOUT)


@pytest.mark.asyncio
async def test_resume_drains_backlog(
    async_session: AsyncSession,
    sample_pipeline,
):
    """Scenario 4: resume process → backlog decreases, eventually empty."""

    async def _run():
        pipeline, steps = sample_pipeline
        sorted_steps = sorted(steps, key=lambda s: s.step_order)
        collect_step, process_step = sorted_steps[0], sorted_steps[1]

        mgr = PipelineManager(db=async_session)
        activation = await mgr.activate_pipeline(pipeline.id)

        lifecycle = StageLifecycleManager(db=async_session)
        await lifecycle.stop_stage(activation.id, process_step.id)

        # Build backlog: 3 items completed collect, waiting for process
        items = await _create_work_items(async_session, activation, pipeline.id, count=3)
        exec_ids = []
        for wi in items:
            eid = await _mark_step_completed(async_session, wi, collect_step)
            exec_ids.append(eid)

        # Verify backlog exists
        summaries = await lifecycle.get_queue_summary(activation.id)
        process_summary = next(s for s in summaries if s.stage_order == process_step.step_order)
        assert process_summary.queued_count >= 3

        # Resume
        await lifecycle.resume_stage(activation.id, process_step.id)

        # Simulate processing: mark process step completed for all items
        for wi, eid in zip(items, exec_ids):
            await _mark_step_completed(async_session, wi, process_step, execution_id=eid)

        # Queue should now be empty (or at least decreased)
        summaries = await lifecycle.get_queue_summary(activation.id)
        process_summary = next(s for s in summaries if s.stage_order == process_step.step_order)
        assert process_summary.queued_count == 0, (
            f"Queue should be empty after drain, got {process_summary.queued_count}"
        )
        assert process_summary.completed_count >= 3

    await asyncio.wait_for(_run(), timeout=TIMEOUT)


@pytest.mark.asyncio
async def test_export_stop_preserves_processed_backlog(
    async_session: AsyncSession,
    sample_pipeline,
):
    """Scenario 5: export stopped → items complete process but queue before export."""

    async def _run():
        pipeline, steps = sample_pipeline
        sorted_steps = sorted(steps, key=lambda s: s.step_order)
        collect_step, process_step, export_step = sorted_steps[0], sorted_steps[1], sorted_steps[2]

        mgr = PipelineManager(db=async_session)
        activation = await mgr.activate_pipeline(pipeline.id)

        lifecycle = StageLifecycleManager(db=async_session)
        await lifecycle.stop_stage(activation.id, export_step.id)

        # Items go through collect + process
        items = await _create_work_items(async_session, activation, pipeline.id, count=3)
        for wi in items:
            eid = await _mark_step_completed(async_session, wi, collect_step)
            await _mark_step_completed(async_session, wi, process_step, execution_id=eid)

        # Check queue
        summaries = await lifecycle.get_queue_summary(activation.id)
        export_summary = next(s for s in summaries if s.stage_order == export_step.step_order)
        assert export_summary.runtime_status == "STOPPED"
        assert export_summary.queued_count >= 3, (
            f"Expected >=3 queued before export, got {export_summary.queued_count}"
        )
        assert export_summary.completed_count == 0

    await asyncio.wait_for(_run(), timeout=TIMEOUT)


@pytest.mark.asyncio
async def test_queue_empty_after_full_drain(
    async_session: AsyncSession,
    sample_pipeline,
):
    """Scenario 8: after resume and drain, all stage queues should be empty."""

    async def _run():
        pipeline, steps = sample_pipeline
        sorted_steps = sorted(steps, key=lambda s: s.step_order)
        collect_step, process_step, export_step = sorted_steps[0], sorted_steps[1], sorted_steps[2]

        mgr = PipelineManager(db=async_session)
        activation = await mgr.activate_pipeline(pipeline.id)

        lifecycle = StageLifecycleManager(db=async_session)

        # Process all items through all stages
        items = await _create_work_items(async_session, activation, pipeline.id, count=2)
        for wi in items:
            eid = await _mark_step_completed(async_session, wi, collect_step)
            await _mark_step_completed(async_session, wi, process_step, execution_id=eid)
            await _mark_step_completed(async_session, wi, export_step, execution_id=eid)

        # All queues should show 0
        summaries = await lifecycle.get_queue_summary(activation.id)
        for s in summaries:
            assert s.queued_count == 0, (
                f"Stage {s.stage_order} ({s.stage_type}) should have empty queue, got {s.queued_count}"
            )
            assert s.runtime_status == "RUNNING"

    await asyncio.wait_for(_run(), timeout=TIMEOUT)
