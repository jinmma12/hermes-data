"""E2E: Reprocess from failed stage — operator recovers after processing failure.

Tests the reprocess journey:
1. Work item fails at process stage
2. Operator creates reprocess request
3. Reprocess runs from the failed stage with updated recipe
4. New execution snapshot is created

All async operations guarded by asyncio.wait_for() to prevent hanging.
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vessel.domain.models.execution import (
    ExecutionSnapshot,
    ReprocessRequest,
    WorkItem,
    WorkItemStepExecution,
)
from vessel.domain.services.pipeline_manager import PipelineManager
from vessel.domain.services.processing_orchestrator import ProcessingOrchestrator
from vessel.domain.services.snapshot_resolver import SnapshotResolver

from .conftest import E2E_TIMEOUT_SECONDS, FakeDispatcher


@pytest.mark.asyncio
async def test_operator_can_request_reprocess_from_specific_stage(
    async_session: AsyncSession,
    e2e_instances,
    pipeline_manager: PipelineManager,
):
    """Reprocess contract: seed failed item, create request, verify persistence."""
    coll_inst, _ = e2e_instances["collector"]
    proc_inst, _ = e2e_instances["processor"]
    exp_inst, _ = e2e_instances["exporter"]

    async def _run():
        # Setup pipeline
        pipeline = await pipeline_manager.create_pipeline(
            name="Reprocess Test Pipeline",
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

        # Create work item and simulate failure at ALGORITHM step
        fail_dispatcher = FakeDispatcher(fail_steps={"ALGORITHM"})
        fail_orchestrator = ProcessingOrchestrator(
            db=async_session,
            dispatcher=fail_dispatcher,
            snapshot_resolver=SnapshotResolver(async_session),
        )

        work_item = WorkItem(
            pipeline_activation_id=activation.id,
            pipeline_instance_id=pipeline.id,
            source_type="FILE",
            source_key="data-001.csv",
            dedup_key="FILE:hash-001",
            status="DETECTED",
        )
        async_session.add(work_item)
        await async_session.flush()

        # First execution: collect succeeds, process fails
        execution1 = await fail_orchestrator.process_work_item(work_item.id)
        assert execution1.status == "FAILED"

        # Verify COLLECT step succeeded but ALGORITHM failed
        stmt = (
            select(WorkItemStepExecution)
            .where(WorkItemStepExecution.execution_id == execution1.id)
            .order_by(WorkItemStepExecution.step_order)
        )
        result = await async_session.execute(stmt)
        step_execs = result.scalars().all()
        assert step_execs[0].step_type == "COLLECT"
        assert step_execs[0].status == "COMPLETED"
        assert step_execs[1].step_type == "ALGORITHM"
        assert step_execs[1].status == "FAILED"
        assert "Simulated ALGORITHM failure" in step_execs[1].error_message

        # Operator creates reprocess request starting from step 2 (process)
        reprocess_req = ReprocessRequest(
            work_item_id=work_item.id,
            requested_by="operator@example.com",
            reason="Fixed algorithm config, retrying from process stage",
            start_from_step=2,
            use_latest_recipe=True,
            status="PENDING",
        )
        async_session.add(reprocess_req)
        await async_session.flush()

        # Verify request persistence
        loaded = await async_session.get(ReprocessRequest, reprocess_req.id)
        assert loaded is not None
        assert loaded.requested_by == "operator@example.com"
        assert loaded.start_from_step == 2
        assert loaded.use_latest_recipe is True
        assert loaded.status == "PENDING"

    await asyncio.wait_for(_run(), timeout=E2E_TIMEOUT_SECONDS)


@pytest.mark.asyncio
async def test_reprocess_executes_from_failed_stage_with_new_snapshot(
    async_session: AsyncSession,
    e2e_instances,
    pipeline_manager: PipelineManager,
):
    """Full reprocess lifecycle: fail -> request -> reprocess -> new snapshot."""
    coll_inst, _ = e2e_instances["collector"]
    proc_inst, _ = e2e_instances["processor"]
    exp_inst, _ = e2e_instances["exporter"]

    async def _run():
        pipeline = await pipeline_manager.create_pipeline(
            name="Full Reprocess Pipeline",
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

        work_item = WorkItem(
            pipeline_activation_id=activation.id,
            pipeline_instance_id=pipeline.id,
            source_type="FILE",
            source_key="data-fail.csv",
            dedup_key="FILE:hash-fail",
            status="DETECTED",
        )
        async_session.add(work_item)
        await async_session.flush()

        # First run: fail at ALGORITHM
        fail_dispatcher = FakeDispatcher(fail_steps={"ALGORITHM"})
        fail_orchestrator = ProcessingOrchestrator(
            db=async_session,
            dispatcher=fail_dispatcher,
            snapshot_resolver=SnapshotResolver(async_session),
        )
        exec1 = await fail_orchestrator.process_work_item(work_item.id)
        assert exec1.status == "FAILED"

        # Create reprocess request
        reprocess_req = ReprocessRequest(
            work_item_id=work_item.id,
            requested_by="operator@example.com",
            reason="Fixed config",
            start_from_step=2,
            use_latest_recipe=True,
            status="PENDING",
        )
        async_session.add(reprocess_req)
        await async_session.flush()

        # Reprocess: all steps succeed this time
        success_dispatcher = FakeDispatcher()
        reprocess_orchestrator = ProcessingOrchestrator(
            db=async_session,
            dispatcher=success_dispatcher,
            snapshot_resolver=SnapshotResolver(async_session),
        )
        exec2 = await reprocess_orchestrator.reprocess_work_item(reprocess_req.id)

        assert exec2.status == "COMPLETED"
        assert exec2.trigger_type == "REPROCESS"
        assert exec2.execution_no == 2
        assert exec2.reprocess_request_id == reprocess_req.id

        # Verify the request was marked DONE
        await async_session.refresh(reprocess_req)
        assert reprocess_req.status == "DONE"
        assert reprocess_req.execution_id == exec2.id

        # Verify step executions: ALGORITHM and TRANSFER ran (COLLECT skipped)
        stmt = (
            select(WorkItemStepExecution)
            .where(WorkItemStepExecution.execution_id == exec2.id)
            .order_by(WorkItemStepExecution.step_order)
        )
        result = await async_session.execute(stmt)
        step_execs = result.scalars().all()
        step_types = [se.step_type for se in step_execs]
        assert "ALGORITHM" in step_types
        assert "TRANSFER" in step_types

        # Verify new snapshot was created
        stmt = select(ExecutionSnapshot).where(
            ExecutionSnapshot.execution_id == exec2.id,
        )
        result = await async_session.execute(stmt)
        snapshot = result.scalar_one_or_none()
        assert snapshot is not None
        assert snapshot.snapshot_hash is not None

        # Verify work item is now COMPLETED
        await async_session.refresh(work_item)
        assert work_item.status == "COMPLETED"

    await asyncio.wait_for(_run(), timeout=E2E_TIMEOUT_SECONDS)


@pytest.mark.asyncio
async def test_operator_can_bulk_reprocess_failed_items(
    async_session: AsyncSession,
    e2e_instances,
    pipeline_manager: PipelineManager,
):
    """Bulk reprocess: create requests for multiple failed items at once."""
    coll_inst, _ = e2e_instances["collector"]
    proc_inst, _ = e2e_instances["processor"]

    async def _run():
        pipeline = await pipeline_manager.create_pipeline(
            name="Bulk Reprocess Pipeline",
            monitoring_type="FTP_MONITOR",
            monitoring_config={"host": "ftp.example.com"},
        )
        await pipeline_manager.add_step(
            pipeline.id, step_type="COLLECT", ref_type="COLLECTOR", ref_id=coll_inst.id,
        )
        await pipeline_manager.add_step(
            pipeline.id, step_type="ALGORITHM", ref_type="ALGORITHM", ref_id=proc_inst.id,
        )
        activation = await pipeline_manager.activate_pipeline(pipeline.id)

        # Create 5 work items
        work_items = []
        for i in range(5):
            wi = WorkItem(
                pipeline_activation_id=activation.id,
                pipeline_instance_id=pipeline.id,
                source_type="FILE",
                source_key=f"bulk-{i:03d}.csv",
                dedup_key=f"FILE:bulk-hash-{i:03d}",
                status="FAILED",
            )
            async_session.add(wi)
            work_items.append(wi)
        await async_session.flush()

        # Bulk reprocess
        bulk_orchestrator = ProcessingOrchestrator(db=async_session)
        requests = await bulk_orchestrator.bulk_reprocess(
            work_item_ids=[wi.id for wi in work_items],
            reason="Batch retry after config fix",
            requested_by="admin@example.com",
            start_from_step=1,
            use_latest_recipe=True,
        )

        assert len(requests) == 5
        assert all(r.status == "PENDING" for r in requests)
        assert all(r.requested_by == "admin@example.com" for r in requests)
        assert all(r.use_latest_recipe is True for r in requests)

    await asyncio.wait_for(_run(), timeout=E2E_TIMEOUT_SECONDS)
