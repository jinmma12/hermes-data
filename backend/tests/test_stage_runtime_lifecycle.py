"""Tests for stage runtime lifecycle: stop/resume vs pipeline deactivate.

Validates the core semantics from STAGE_LIFECYCLE_AND_QUEUE_MODEL.md:
- pipeline deactivate stops whole activation
- stage stop does NOT deactivate whole pipeline
- stopped stage and disabled stage are different concepts
- stage runtime state initializes on activation
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from hermes.domain.services.pipeline_manager import PipelineManager
from hermes.domain.services.stage_lifecycle import StageLifecycleManager

TIMEOUT = 10


@pytest.mark.asyncio
async def test_pipeline_deactivate_stops_whole_activation(
    async_session: AsyncSession,
    sample_pipeline,
):
    """Scenario 1: deactivate_pipeline sets activation STOPPED and pipeline PAUSED."""

    async def _run():
        pipeline, steps = sample_pipeline
        mgr = PipelineManager(db=async_session)
        activation = await mgr.activate_pipeline(pipeline.id)

        await mgr.deactivate_pipeline(pipeline.id)
        await async_session.refresh(activation)

        assert activation.status == "STOPPED"
        assert activation.stopped_at is not None

        status = await mgr.get_pipeline_status(pipeline.id)
        assert status.status == "PAUSED"

    await asyncio.wait_for(_run(), timeout=TIMEOUT)


@pytest.mark.asyncio
async def test_stage_stop_does_not_deactivate_pipeline(
    async_session: AsyncSession,
    sample_pipeline,
):
    """Scenario 2: stopping a stage keeps pipeline activation RUNNING."""

    async def _run():
        pipeline, steps = sample_pipeline
        mgr = PipelineManager(db=async_session)
        activation = await mgr.activate_pipeline(pipeline.id)

        lifecycle = StageLifecycleManager(db=async_session)
        # Stop the second stage (process/algorithm)
        process_step = sorted(steps, key=lambda s: s.step_order)[1]
        state = await lifecycle.stop_stage(activation.id, process_step.id, stopped_by="operator")

        assert state.runtime_status == "STOPPED"
        assert state.stopped_by == "operator"

        # Pipeline activation must still be RUNNING (or STARTING)
        await async_session.refresh(activation)
        assert activation.status in ("STARTING", "RUNNING"), (
            f"Stage stop must not change activation status, got {activation.status}"
        )

        # Other stages should still be RUNNING
        collect_step = sorted(steps, key=lambda s: s.step_order)[0]
        collect_state = await lifecycle.get_stage_runtime(activation.id, collect_step.id)
        assert collect_state is not None
        assert collect_state.runtime_status == "RUNNING"

    await asyncio.wait_for(_run(), timeout=TIMEOUT)


@pytest.mark.asyncio
async def test_stage_resume_sets_running(
    async_session: AsyncSession,
    sample_pipeline,
):
    """Stop then resume a stage — runtime_status goes back to RUNNING."""

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
async def test_disabled_stage_vs_stopped_stage(
    async_session: AsyncSession,
    sample_pipeline,
):
    """Scenario 9: disabled (is_enabled=false) and stopped (runtime STOPPED) are different."""

    async def _run():
        pipeline, steps = sample_pipeline
        mgr = PipelineManager(db=async_session)
        activation = await mgr.activate_pipeline(pipeline.id)

        lifecycle = StageLifecycleManager(db=async_session)
        process_step = sorted(steps, key=lambda s: s.step_order)[1]

        # Stop the stage at runtime
        state = await lifecycle.stop_stage(activation.id, process_step.id)
        assert state.runtime_status == "STOPPED"

        # The static config flag should still be True
        await async_session.refresh(process_step)
        assert process_step.is_enabled is True, (
            "Stage stop must not alter is_enabled config flag"
        )

    await asyncio.wait_for(_run(), timeout=TIMEOUT)


@pytest.mark.asyncio
async def test_activation_initializes_stage_states(
    async_session: AsyncSession,
    sample_pipeline,
):
    """activate_pipeline should create RUNNING runtime states for all steps."""

    async def _run():
        pipeline, steps = sample_pipeline
        mgr = PipelineManager(db=async_session)
        activation = await mgr.activate_pipeline(pipeline.id)

        lifecycle = StageLifecycleManager(db=async_session)
        for step in steps:
            state = await lifecycle.get_stage_runtime(activation.id, step.id)
            assert state is not None, f"No runtime state for step {step.id}"
            assert state.runtime_status == "RUNNING"

    await asyncio.wait_for(_run(), timeout=TIMEOUT)
