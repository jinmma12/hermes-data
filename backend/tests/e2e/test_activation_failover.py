"""E2E: Activation failover — deactivate/reactivate and checkpoint semantics.

Cluster-level failover (coordinator lease, worker crash) requires the .NET
engine. These tests verify the Python reference layer's activation lifecycle
and checkpoint contracts at the service layer.

Tests that require actual multi-node behavior remain xfail.
All async operations guarded by asyncio.wait_for() to prevent hanging.
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from vessel.domain.models.execution import WorkItem
from vessel.domain.services.pipeline_manager import PipelineManager

from .conftest import E2E_TIMEOUT_SECONDS


@pytest.mark.asyncio
async def test_deactivate_and_reactivate_pipeline(
    async_session: AsyncSession,
    e2e_instances,
    pipeline_manager: PipelineManager,
):
    """Operator can deactivate and reactivate a pipeline, creating new activations."""
    coll_inst, _ = e2e_instances["collector"]
    proc_inst, _ = e2e_instances["processor"]

    async def _run():
        pipeline = await pipeline_manager.create_pipeline(
            name="Failover Test Pipeline",
            monitoring_type="FTP_MONITOR",
            monitoring_config={"host": "ftp.example.com"},
        )
        await pipeline_manager.add_step(
            pipeline.id, step_type="COLLECT", ref_type="COLLECTOR", ref_id=coll_inst.id,
        )
        await pipeline_manager.add_step(
            pipeline.id, step_type="ALGORITHM", ref_type="ALGORITHM", ref_id=proc_inst.id,
        )

        # Activate
        activation1 = await pipeline_manager.activate_pipeline(pipeline.id, worker_id="worker-A")
        assert activation1.status == "STARTING"

        # Deactivate
        await pipeline_manager.deactivate_pipeline(pipeline.id)
        await async_session.refresh(activation1)
        assert activation1.status == "STOPPED"
        assert activation1.stopped_at is not None

        status = await pipeline_manager.get_pipeline_status(pipeline.id)
        assert status.status == "PAUSED"

        # Reactivate on different worker
        activation2 = await pipeline_manager.activate_pipeline(pipeline.id, worker_id="worker-B")
        assert activation2.id != activation1.id
        assert activation2.worker_id == "worker-B"
        assert activation2.status == "STARTING"

        status = await pipeline_manager.get_pipeline_status(pipeline.id)
        assert status.status == "ACTIVE"
        assert status.active_activation_id == activation2.id

    await asyncio.wait_for(_run(), timeout=E2E_TIMEOUT_SECONDS)


@pytest.mark.asyncio
async def test_activation_preserves_work_items_across_restart(
    async_session: AsyncSession,
    e2e_instances,
    pipeline_manager: PipelineManager,
):
    """Work items from a previous activation are visible after reactivation."""
    coll_inst, _ = e2e_instances["collector"]

    async def _run():
        pipeline = await pipeline_manager.create_pipeline(
            name="Restart Persistence Test",
            monitoring_type="FILE_MONITOR",
        )
        await pipeline_manager.add_step(
            pipeline.id, step_type="COLLECT", ref_type="COLLECTOR", ref_id=coll_inst.id,
        )

        # First activation: create work items
        activation1 = await pipeline_manager.activate_pipeline(pipeline.id)
        for i in range(3):
            wi = WorkItem(
                pipeline_activation_id=activation1.id,
                pipeline_instance_id=pipeline.id,
                source_type="FILE",
                source_key=f"restart-{i}.csv",
                dedup_key=f"FILE:restart-{i}",
                status="DETECTED",
            )
            async_session.add(wi)
        await async_session.flush()

        # Deactivate and reactivate
        await pipeline_manager.deactivate_pipeline(pipeline.id)
        await pipeline_manager.activate_pipeline(pipeline.id)

        # Work items from first activation should still be queryable
        status = await pipeline_manager.get_pipeline_status(pipeline.id)
        assert status.work_item_count == 3, (
            "Work items must persist across activation cycles"
        )

    await asyncio.wait_for(_run(), timeout=E2E_TIMEOUT_SECONDS)


@pytest.mark.asyncio
async def test_deactivate_nonexistent_raises_error(
    async_session: AsyncSession,
    e2e_instances,
    pipeline_manager: PipelineManager,
):
    """Deactivating a pipeline with no active activation raises ValueError."""
    coll_inst, _ = e2e_instances["collector"]

    async def _run():
        pipeline = await pipeline_manager.create_pipeline(
            name="No Active Activation",
            monitoring_type="FILE_MONITOR",
        )
        await pipeline_manager.add_step(
            pipeline.id, step_type="COLLECT", ref_type="COLLECTOR", ref_id=coll_inst.id,
        )

        with pytest.raises(ValueError, match="No active activation"):
            await pipeline_manager.deactivate_pipeline(pipeline.id)

    await asyncio.wait_for(_run(), timeout=E2E_TIMEOUT_SECONDS)


@pytest.mark.xfail(
    reason="Cluster coordinator lease and failover require .NET engine runtime",
    strict=False,
)
@pytest.mark.asyncio
async def test_failover_reassigns_active_pipeline_without_duplicate_collection():
    """Requires multi-node lease/checkpoint from .NET engine.

    Cannot be tested in the Python reference layer alone because:
    - Lease-based coordinator election is an engine-level concern
    - Checkpoint persistence across nodes requires shared DB state from engine
    - Duplicate collection detection needs the engine's monitor state machine

    Target: engine/tests/Hermes.Engine.Tests/Cluster/CheckpointFailoverTests.cs
    """
    raise NotImplementedError("Requires .NET engine runtime")


@pytest.mark.xfail(
    reason="Worker crash recovery requires .NET engine's persisted checkpoint resume",
    strict=False,
)
@pytest.mark.asyncio
async def test_worker_crash_after_collect_resumes_export_without_recollecting():
    """Requires .NET engine's step-level checkpoint and recovery.

    Target: engine/tests/Hermes.Engine.Tests/Cluster/CheckpointFailoverTests.cs
    """
    raise NotImplementedError("Requires .NET engine runtime")
