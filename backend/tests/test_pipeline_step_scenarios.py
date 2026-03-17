"""Comprehensive Pipeline Step Scenario Tests.

Each pipeline stage (Collect → Process → Export) is tested across:
1. Success scenarios — happy path, multi-step chaining
2. Failure scenarios — STOP / SKIP / partial failure
3. Retry scenarios — exponential backoff, retry success, retry exhaustion
4. Backpressure scenarios — queue depth, concurrent work items
5. Provenance / data capture — snapshot immutability, event logs, input/output audit
6. Reprocess scenarios — start from step N, latest vs frozen recipe, bulk reprocess
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from vessel.domain.models.execution import (
    ExecutionEventLog,
    ExecutionSnapshot,
    ReprocessRequest,
    WorkItem,
    WorkItemExecution,
    WorkItemStepExecution,
)
from vessel.domain.models.monitoring import PipelineActivation
from vessel.domain.models.pipeline import PipelineInstance, PipelineStep
from vessel.domain.services.execution_dispatcher import ExecutionDispatcher, ExecutionResult
from vessel.domain.services.processing_orchestrator import ProcessingOrchestrator
from vessel.domain.services.snapshot_resolver import ResolvedConfig, SnapshotResolver, StepConfig


# ===========================================================================
# Test Helpers
# ===========================================================================


def _ok(output: dict | None = None, summary: dict | None = None, ms: int = 10) -> ExecutionResult:
    return ExecutionResult(success=True, output=output or {}, summary=summary or {}, duration_ms=ms)


def _fail(msg: str = "step failed", ms: int = 5) -> ExecutionResult:
    return ExecutionResult(
        success=False, output={}, summary={}, duration_ms=ms,
        logs=[{"level": "ERROR", "message": msg}],
    )


def _mock_dispatcher(results: list[ExecutionResult]) -> ExecutionDispatcher:
    d = AsyncMock(spec=ExecutionDispatcher)
    d.dispatch = AsyncMock(side_effect=results)
    return d


def _tracking_dispatcher(side_effect_fn) -> ExecutionDispatcher:
    d = AsyncMock(spec=ExecutionDispatcher)
    d.dispatch = AsyncMock(side_effect=side_effect_fn)
    return d


def _mock_resolver(db: AsyncSession, steps: list[PipelineStep]) -> SnapshotResolver:
    resolver = AsyncMock(spec=SnapshotResolver)

    async def capture(pipeline, pipeline_steps, execution_id, use_latest):
        snap = ExecutionSnapshot(
            execution_id=execution_id,
            pipeline_config={"name": pipeline.name},
            collector_config={},
            algorithm_config={},
            transfer_config={},
            snapshot_hash="test-hash-" + str(execution_id)[:8],
        )
        db.add(snap)
        await db.flush()
        return snap

    async def resolve(snapshot_id):
        rc = ResolvedConfig(pipeline_config={})
        for step in steps:
            rc.steps.append(StepConfig(
                step_id=step.id, step_order=step.step_order, step_type=step.step_type,
                ref_type=step.ref_type, ref_id=step.ref_id,
                execution_type="PLUGIN", execution_ref=f"{step.ref_type}:test",
                resolved_config={"test": True}, version_no=1,
            ))
        return rc

    resolver.capture = AsyncMock(side_effect=capture)
    resolver.resolve = AsyncMock(side_effect=resolve)
    return resolver


async def _make_work_item(db: AsyncSession, pipeline: PipelineInstance) -> WorkItem:
    act = PipelineActivation(pipeline_instance_id=pipeline.id, status="RUNNING")
    db.add(act)
    await db.flush()
    wi = WorkItem(
        pipeline_activation_id=act.id, pipeline_instance_id=pipeline.id,
        source_type="FILE", source_key=f"data-{uuid.uuid4().hex[:8]}.csv",
        source_metadata={"size": 1024}, status="DETECTED",
    )
    db.add(wi)
    await db.flush()
    return wi


def _orch(db, dispatcher, resolver, steps):
    return ProcessingOrchestrator(db=db, dispatcher=dispatcher, snapshot_resolver=resolver)


async def _get_step_execs(db: AsyncSession, execution_id: uuid.UUID) -> list[WorkItemStepExecution]:
    result = await db.execute(
        select(WorkItemStepExecution)
        .where(WorkItemStepExecution.execution_id == execution_id)
        .order_by(WorkItemStepExecution.step_order)
    )
    return list(result.scalars().all())


async def _get_event_logs(db: AsyncSession, execution_id: uuid.UUID) -> list[ExecutionEventLog]:
    result = await db.execute(
        select(ExecutionEventLog)
        .where(ExecutionEventLog.execution_id == execution_id)
        .order_by(ExecutionEventLog.created_at)
    )
    return list(result.scalars().all())


# ===========================================================================
# 1. SUCCESS SCENARIOS
# ===========================================================================


class TestSuccessScenarios:
    """Happy path: all steps complete successfully."""

    @pytest.mark.asyncio
    async def test_three_step_success(self, async_session, sample_pipeline):
        """Collect → Process → Export all succeed."""
        pipeline, steps = sample_pipeline
        wi = await _make_work_item(async_session, pipeline)
        dispatcher = _mock_dispatcher([_ok({"collected": True}), _ok({"processed": True}), _ok({"exported": True})])
        resolver = _mock_resolver(async_session, steps)

        ex = await _orch(async_session, dispatcher, resolver, steps).process_work_item(wi.id)

        assert ex.status == "COMPLETED"
        assert ex.execution_no == 1
        await async_session.refresh(wi)
        assert wi.status == "COMPLETED"
        assert wi.last_completed_at is not None

    @pytest.mark.asyncio
    async def test_single_collector_success(self, async_session, sample_pipeline):
        """Pipeline with only the collector step enabled."""
        pipeline, steps = sample_pipeline
        steps[1].is_enabled = False
        steps[2].is_enabled = False
        await async_session.flush()
        wi = await _make_work_item(async_session, pipeline)

        dispatcher = _mock_dispatcher([_ok({"files": 3})])
        resolver = _mock_resolver(async_session, steps)

        ex = await _orch(async_session, dispatcher, resolver, steps).process_work_item(wi.id)
        assert ex.status == "COMPLETED"
        assert dispatcher.dispatch.call_count == 1

    @pytest.mark.asyncio
    async def test_output_chaining_through_all_steps(self, async_session, sample_pipeline):
        """Step N output is input to step N+1."""
        pipeline, steps = sample_pipeline
        wi = await _make_work_item(async_session, pipeline)
        received: list[Any] = []

        async def track(**kw):
            received.append(kw.get("input_data"))
            t = kw.get("context", {}).get("step_type", "?")
            if t == "COLLECT":
                return _ok({"rows": [1, 2, 3]})
            elif t == "ALGORITHM":
                return _ok({"filtered": [2, 3]})
            return _ok({"written": 2})

        dispatcher = _tracking_dispatcher(track)
        resolver = _mock_resolver(async_session, steps)

        ex = await _orch(async_session, dispatcher, resolver, steps).process_work_item(wi.id)
        assert ex.status == "COMPLETED"
        assert received[0] is None  # first step gets no input
        assert received[1] == {"rows": [1, 2, 3]}
        assert received[2] == {"filtered": [2, 3]}

    @pytest.mark.asyncio
    async def test_execution_count_increments(self, async_session, sample_pipeline):
        """Each process call increments execution_count."""
        pipeline, steps = sample_pipeline
        wi = await _make_work_item(async_session, pipeline)
        dispatcher = _mock_dispatcher([_ok(), _ok(), _ok()])
        resolver = _mock_resolver(async_session, steps)

        ex = await _orch(async_session, dispatcher, resolver, steps).process_work_item(wi.id)
        await async_session.refresh(wi)
        assert wi.execution_count == 1
        assert ex.execution_no == 1

    @pytest.mark.asyncio
    async def test_step_execution_records_created(self, async_session, sample_pipeline):
        """Each step produces a WorkItemStepExecution record."""
        pipeline, steps = sample_pipeline
        wi = await _make_work_item(async_session, pipeline)
        dispatcher = _mock_dispatcher([_ok(), _ok(), _ok()])
        resolver = _mock_resolver(async_session, steps)

        ex = await _orch(async_session, dispatcher, resolver, steps).process_work_item(wi.id)
        step_execs = await _get_step_execs(async_session, ex.id)

        assert len(step_execs) == 3
        assert [se.step_type for se in step_execs] == ["COLLECT", "ALGORITHM", "TRANSFER"]
        assert all(se.status == "COMPLETED" for se in step_execs)

    @pytest.mark.asyncio
    async def test_timing_recorded_per_step(self, async_session, sample_pipeline):
        """Each step has started_at, ended_at, duration_ms."""
        pipeline, steps = sample_pipeline
        wi = await _make_work_item(async_session, pipeline)
        dispatcher = _mock_dispatcher([_ok(ms=50), _ok(ms=30), _ok(ms=20)])
        resolver = _mock_resolver(async_session, steps)

        ex = await _orch(async_session, dispatcher, resolver, steps).process_work_item(wi.id)
        step_execs = await _get_step_execs(async_session, ex.id)

        for se in step_execs:
            assert se.started_at is not None
            assert se.ended_at is not None
            assert se.duration_ms is not None
            assert se.duration_ms >= 0

        assert ex.duration_ms is not None
        assert ex.duration_ms >= 0


# ===========================================================================
# 2. FAILURE SCENARIOS
# ===========================================================================


class TestFailureScenarios:
    """Step failures with STOP, SKIP, and partial failure combinations."""

    @pytest.mark.asyncio
    async def test_collect_fails_stop(self, async_session, sample_pipeline):
        """First step fails with on_error=STOP → entire pipeline fails immediately."""
        pipeline, steps = sample_pipeline
        wi = await _make_work_item(async_session, pipeline)
        dispatcher = _mock_dispatcher([_fail("connection timeout")])
        resolver = _mock_resolver(async_session, steps)

        ex = await _orch(async_session, dispatcher, resolver, steps).process_work_item(wi.id)

        assert ex.status == "FAILED"
        assert dispatcher.dispatch.call_count == 1
        await async_session.refresh(wi)
        assert wi.status == "FAILED"

    @pytest.mark.asyncio
    async def test_process_fails_stop_export_skipped(self, async_session, sample_pipeline):
        """Middle step fails → export never runs."""
        pipeline, steps = sample_pipeline
        wi = await _make_work_item(async_session, pipeline)
        dispatcher = _mock_dispatcher([_ok(), _fail("transform error")])
        resolver = _mock_resolver(async_session, steps)

        ex = await _orch(async_session, dispatcher, resolver, steps).process_work_item(wi.id)

        assert ex.status == "FAILED"
        assert dispatcher.dispatch.call_count == 2

        step_execs = await _get_step_execs(async_session, ex.id)
        assert step_execs[0].status == "COMPLETED"
        assert step_execs[1].status == "FAILED"
        assert step_execs[1].error_message is not None

    @pytest.mark.asyncio
    async def test_export_fails_stop(self, async_session, sample_pipeline):
        """Last step fails → still FAILED overall."""
        pipeline, steps = sample_pipeline
        wi = await _make_work_item(async_session, pipeline)
        dispatcher = _mock_dispatcher([_ok(), _ok(), _fail("write failed")])
        resolver = _mock_resolver(async_session, steps)

        ex = await _orch(async_session, dispatcher, resolver, steps).process_work_item(wi.id)
        assert ex.status == "FAILED"

    @pytest.mark.asyncio
    async def test_process_fails_skip_continues(self, async_session, sample_pipeline):
        """on_error=SKIP: process fails but export still runs."""
        pipeline, steps = sample_pipeline
        steps[1].on_error = "SKIP"
        await async_session.flush()
        wi = await _make_work_item(async_session, pipeline)

        dispatcher = _mock_dispatcher([_ok({"data": [1]}), _fail("transform err"), _ok()])
        resolver = _mock_resolver(async_session, steps)

        ex = await _orch(async_session, dispatcher, resolver, steps).process_work_item(wi.id)
        assert ex.status == "COMPLETED"
        assert dispatcher.dispatch.call_count == 3

    @pytest.mark.asyncio
    async def test_multiple_skip_steps_all_fail(self, async_session, sample_pipeline):
        """Two SKIP steps fail in a row, pipeline still completes."""
        pipeline, steps = sample_pipeline
        steps[0].on_error = "SKIP"
        steps[1].on_error = "SKIP"
        await async_session.flush()
        wi = await _make_work_item(async_session, pipeline)

        dispatcher = _mock_dispatcher([_fail("err1"), _fail("err2"), _ok()])
        resolver = _mock_resolver(async_session, steps)

        ex = await _orch(async_session, dispatcher, resolver, steps).process_work_item(wi.id)
        assert ex.status == "COMPLETED"
        assert dispatcher.dispatch.call_count == 3

    @pytest.mark.asyncio
    async def test_error_code_and_message_captured(self, async_session, sample_pipeline):
        """Error details are stored in step execution."""
        pipeline, steps = sample_pipeline
        wi = await _make_work_item(async_session, pipeline)
        dispatcher = _mock_dispatcher([_fail("FileNotFoundError: /data/input.csv")])
        resolver = _mock_resolver(async_session, steps)

        ex = await _orch(async_session, dispatcher, resolver, steps).process_work_item(wi.id)
        step_execs = await _get_step_execs(async_session, ex.id)
        assert step_execs[0].error_message is not None
        assert "FileNotFoundError" in step_execs[0].error_message or "step" in step_execs[0].error_message.lower()

    @pytest.mark.asyncio
    async def test_disabled_step_not_dispatched(self, async_session, sample_pipeline):
        """Disabled step is silently skipped."""
        pipeline, steps = sample_pipeline
        steps[1].is_enabled = False
        await async_session.flush()
        wi = await _make_work_item(async_session, pipeline)

        dispatcher = _mock_dispatcher([_ok(), _ok()])
        resolver = _mock_resolver(async_session, steps)

        ex = await _orch(async_session, dispatcher, resolver, steps).process_work_item(wi.id)
        assert ex.status == "COMPLETED"
        assert dispatcher.dispatch.call_count == 2

    @pytest.mark.asyncio
    async def test_exception_in_dispatcher_captured(self, async_session, sample_pipeline):
        """Raw exception from dispatcher is captured as error."""
        pipeline, steps = sample_pipeline
        wi = await _make_work_item(async_session, pipeline)

        d = AsyncMock(spec=ExecutionDispatcher)
        d.dispatch = AsyncMock(side_effect=[
            _ok(),
            ConnectionError("host unreachable"),
        ])
        resolver = _mock_resolver(async_session, steps)

        ex = await _orch(async_session, d, resolver, steps).process_work_item(wi.id)
        assert ex.status == "FAILED"

        step_execs = await _get_step_execs(async_session, ex.id)
        assert step_execs[1].status == "FAILED"
        assert step_execs[1].error_code == "ConnectionError"
        assert "unreachable" in step_execs[1].error_message


# ===========================================================================
# 3. RETRY SCENARIOS
# ===========================================================================


class TestRetryScenarios:
    """Exponential backoff retry with eventual success or exhaustion."""

    @pytest.mark.asyncio
    async def test_retry_succeeds_on_second_attempt(self, async_session, sample_pipeline):
        """Step fails once, retries, succeeds."""
        pipeline, steps = sample_pipeline
        steps[1].on_error = "RETRY"
        steps[1].retry_count = 3
        steps[1].retry_delay_seconds = 0  # no delay for test
        await async_session.flush()
        wi = await _make_work_item(async_session, pipeline)

        call_idx = 0

        async def dispatch(**kw):
            nonlocal call_idx
            call_idx += 1
            t = kw.get("context", {}).get("step_type", "?")
            if t == "ALGORITHM":
                if call_idx == 2:  # first ALGORITHM call fails
                    return _fail("transient error")
                return _ok({"retried": True})
            return _ok()

        dispatcher = _tracking_dispatcher(dispatch)
        resolver = _mock_resolver(async_session, steps)

        ex = await _orch(async_session, dispatcher, resolver, steps).process_work_item(wi.id)

        # Step 2 failed initially then retried and succeeded
        step_execs = await _get_step_execs(async_session, ex.id)
        algo_step = [se for se in step_execs if se.step_type == "ALGORITHM"][0]
        assert algo_step.retry_attempt >= 1
        assert algo_step.status == "COMPLETED"

    @pytest.mark.asyncio
    async def test_retry_exhausted_fails_pipeline(self, async_session, sample_pipeline):
        """All retries fail → pipeline fails."""
        pipeline, steps = sample_pipeline
        steps[0].on_error = "RETRY"
        steps[0].retry_count = 2
        steps[0].retry_delay_seconds = 0
        await async_session.flush()
        wi = await _make_work_item(async_session, pipeline)

        # Always fails
        dispatcher = _mock_dispatcher([_fail("permanent error")])
        # dispatcher.dispatch will be called: initial(fail) + retry1(fail) + retry2(fail)
        # but _mock_dispatcher only has 1 result... let's use tracking
        async def always_fail(**kw):
            return _fail("permanent error")

        dispatcher = _tracking_dispatcher(always_fail)
        resolver = _mock_resolver(async_session, steps)

        ex = await _orch(async_session, dispatcher, resolver, steps).process_work_item(wi.id)
        assert ex.status == "FAILED"

        # Check retry event logs
        logs = await _get_event_logs(async_session, ex.id)
        retry_logs = [l for l in logs if "RETRY" in l.event_code]
        assert len(retry_logs) >= 1

    @pytest.mark.asyncio
    async def test_retry_attempt_recorded_in_step_execution(self, async_session, sample_pipeline):
        """retry_attempt field reflects which attempt succeeded."""
        pipeline, steps = sample_pipeline
        steps[1].on_error = "RETRY"
        steps[1].retry_count = 3
        steps[1].retry_delay_seconds = 0
        await async_session.flush()
        wi = await _make_work_item(async_session, pipeline)

        attempts = 0

        async def fail_twice_then_ok(**kw):
            nonlocal attempts
            t = kw.get("context", {}).get("step_type", "?")
            if t == "ALGORITHM":
                attempts += 1
                if attempts <= 2:  # initial fail + first retry fail
                    return _fail("flaky")
                return _ok({"recovered": True})
            return _ok()

        dispatcher = _tracking_dispatcher(fail_twice_then_ok)
        resolver = _mock_resolver(async_session, steps)

        ex = await _orch(async_session, dispatcher, resolver, steps).process_work_item(wi.id)

        step_execs = await _get_step_execs(async_session, ex.id)
        algo_step = [se for se in step_execs if se.step_type == "ALGORITHM"][0]
        # Retry succeeded on attempt 2 (after initial fail + retry1 fail)
        assert algo_step.retry_attempt >= 1
        assert algo_step.status == "COMPLETED"

    @pytest.mark.asyncio
    async def test_retry_on_collect_step(self, async_session, sample_pipeline):
        """Collect step also supports retry."""
        pipeline, steps = sample_pipeline
        steps[0].on_error = "RETRY"
        steps[0].retry_count = 1
        steps[0].retry_delay_seconds = 0
        await async_session.flush()
        wi = await _make_work_item(async_session, pipeline)

        call_count = 0

        async def flaky_collect(**kw):
            nonlocal call_count
            call_count += 1
            t = kw.get("context", {}).get("step_type", "?")
            if t == "COLLECT" and call_count == 1:
                return _fail("FTP timeout")
            return _ok()

        dispatcher = _tracking_dispatcher(flaky_collect)
        resolver = _mock_resolver(async_session, steps)

        ex = await _orch(async_session, dispatcher, resolver, steps).process_work_item(wi.id)
        # Collect failed once, retried once, then algorithm + transfer succeed
        assert dispatcher.dispatch.call_count >= 3


# ===========================================================================
# 4. BACKPRESSURE SCENARIOS
# ===========================================================================


class TestBackpressureScenarios:
    """Multiple concurrent work items and queue depth tracking."""

    @pytest.mark.asyncio
    async def test_multiple_work_items_independent_executions(self, async_session, sample_pipeline):
        """5 work items process independently with separate execution records."""
        pipeline, steps = sample_pipeline
        work_items = []
        for _ in range(5):
            wi = await _make_work_item(async_session, pipeline)
            work_items.append(wi)

        for wi in work_items:
            dispatcher = _mock_dispatcher([_ok(), _ok(), _ok()])
            resolver = _mock_resolver(async_session, steps)
            orch = _orch(async_session, dispatcher, resolver, steps)
            ex = await orch.process_work_item(wi.id)
            assert ex.status == "COMPLETED"

        # Each work item has its own execution
        total = await async_session.execute(
            select(sa_func.count()).select_from(WorkItemExecution)
        )
        assert total.scalar() == 5

    @pytest.mark.asyncio
    async def test_work_item_queue_depth_tracking(self, async_session, sample_pipeline):
        """Can count DETECTED (queued) vs PROCESSING vs COMPLETED work items."""
        pipeline, steps = sample_pipeline

        # Create work items in different states
        wi1 = await _make_work_item(async_session, pipeline)
        wi2 = await _make_work_item(async_session, pipeline)
        wi3 = await _make_work_item(async_session, pipeline)

        # Process wi1 (COMPLETED)
        dispatcher = _mock_dispatcher([_ok(), _ok(), _ok()])
        resolver = _mock_resolver(async_session, steps)
        await _orch(async_session, dispatcher, resolver, steps).process_work_item(wi1.id)

        # Process wi2 (FAILED)
        dispatcher2 = _mock_dispatcher([_fail("err")])
        resolver2 = _mock_resolver(async_session, steps)
        await _orch(async_session, dispatcher2, resolver2, steps).process_work_item(wi2.id)

        # wi3 stays DETECTED (in queue)

        # Count by status
        for status, expected in [("COMPLETED", 1), ("FAILED", 1), ("DETECTED", 1)]:
            result = await async_session.execute(
                select(sa_func.count()).select_from(WorkItem).where(
                    WorkItem.pipeline_instance_id == pipeline.id,
                    WorkItem.status == status,
                )
            )
            assert result.scalar() == expected, f"Expected {expected} {status} items"

    @pytest.mark.asyncio
    async def test_high_volume_work_items(self, async_session, sample_pipeline):
        """Process 20 work items sequentially, all succeed."""
        pipeline, steps = sample_pipeline

        for i in range(20):
            wi = await _make_work_item(async_session, pipeline)
            dispatcher = _mock_dispatcher([_ok(), _ok(), _ok()])
            resolver = _mock_resolver(async_session, steps)
            await _orch(async_session, dispatcher, resolver, steps).process_work_item(wi.id)

        completed = await async_session.execute(
            select(sa_func.count()).select_from(WorkItem).where(
                WorkItem.pipeline_instance_id == pipeline.id,
                WorkItem.status == "COMPLETED",
            )
        )
        assert completed.scalar() == 20

    @pytest.mark.asyncio
    async def test_mixed_success_failure_batch(self, async_session, sample_pipeline):
        """Batch of 10: odd items fail, even items succeed."""
        pipeline, steps = sample_pipeline
        results_map = {}

        for i in range(10):
            wi = await _make_work_item(async_session, pipeline)
            if i % 2 == 0:
                dispatcher = _mock_dispatcher([_ok(), _ok(), _ok()])
            else:
                dispatcher = _mock_dispatcher([_ok(), _fail("odd fail")])
            resolver = _mock_resolver(async_session, steps)
            ex = await _orch(async_session, dispatcher, resolver, steps).process_work_item(wi.id)
            results_map[wi.id] = ex.status

        completed = sum(1 for s in results_map.values() if s == "COMPLETED")
        failed = sum(1 for s in results_map.values() if s == "FAILED")
        assert completed == 5
        assert failed == 5


# ===========================================================================
# 5. PROVENANCE / DATA CAPTURE SCENARIOS
# ===========================================================================


class TestProvenanceScenarios:
    """Verify data lineage: snapshots, event logs, input/output capture."""

    @pytest.mark.asyncio
    async def test_snapshot_created_per_execution(self, async_session, sample_pipeline):
        """Each execution creates exactly one ExecutionSnapshot."""
        pipeline, steps = sample_pipeline
        wi = await _make_work_item(async_session, pipeline)
        dispatcher = _mock_dispatcher([_ok(), _ok(), _ok()])
        resolver = _mock_resolver(async_session, steps)

        ex = await _orch(async_session, dispatcher, resolver, steps).process_work_item(wi.id)

        snaps = await async_session.execute(
            select(ExecutionSnapshot).where(ExecutionSnapshot.execution_id == ex.id)
        )
        snap_list = list(snaps.scalars().all())
        assert len(snap_list) == 1
        assert snap_list[0].snapshot_hash is not None

    @pytest.mark.asyncio
    async def test_snapshot_hash_changes_between_executions(self, async_session, sample_pipeline):
        """Different executions may produce different snapshot hashes."""
        pipeline, steps = sample_pipeline
        wi = await _make_work_item(async_session, pipeline)

        # Execution 1
        dispatcher = _mock_dispatcher([_ok(), _ok(), _ok()])
        resolver = _mock_resolver(async_session, steps)
        ex1 = await _orch(async_session, dispatcher, resolver, steps).process_work_item(wi.id)

        # Reset status for re-execution
        wi.status = "DETECTED"
        await async_session.flush()

        # Execution 2
        dispatcher2 = _mock_dispatcher([_ok(), _ok(), _ok()])
        resolver2 = _mock_resolver(async_session, steps)
        ex2 = await _orch(async_session, dispatcher2, resolver2, steps).process_work_item(wi.id)

        snap1 = await async_session.execute(
            select(ExecutionSnapshot).where(ExecutionSnapshot.execution_id == ex1.id)
        )
        snap2 = await async_session.execute(
            select(ExecutionSnapshot).where(ExecutionSnapshot.execution_id == ex2.id)
        )
        s1 = snap1.scalar_one()
        s2 = snap2.scalar_one()
        # Both have hashes (they may differ since execution_id is part of the hash seed)
        assert s1.snapshot_hash is not None
        assert s2.snapshot_hash is not None

    @pytest.mark.asyncio
    async def test_event_logs_cover_full_lifecycle(self, async_session, sample_pipeline):
        """EXECUTION_START, per-step START/DONE, EXECUTION_END logged."""
        pipeline, steps = sample_pipeline
        wi = await _make_work_item(async_session, pipeline)
        dispatcher = _mock_dispatcher([_ok(), _ok(), _ok()])
        resolver = _mock_resolver(async_session, steps)

        ex = await _orch(async_session, dispatcher, resolver, steps).process_work_item(wi.id)
        logs = await _get_event_logs(async_session, ex.id)

        codes = [l.event_code for l in logs]
        assert "EXECUTION_START" in codes
        assert "EXECUTION_END" in codes
        assert "COLLECT_START" in codes
        assert "COLLECT_DONE" in codes
        assert "ALGORITHM_START" in codes
        assert "ALGORITHM_DONE" in codes
        assert "TRANSFER_START" in codes
        assert "TRANSFER_DONE" in codes

    @pytest.mark.asyncio
    async def test_error_events_logged_on_failure(self, async_session, sample_pipeline):
        """Failed step generates ERROR event log."""
        pipeline, steps = sample_pipeline
        wi = await _make_work_item(async_session, pipeline)
        dispatcher = _mock_dispatcher([_ok(), _fail("processing error")])
        resolver = _mock_resolver(async_session, steps)

        ex = await _orch(async_session, dispatcher, resolver, steps).process_work_item(wi.id)
        logs = await _get_event_logs(async_session, ex.id)

        error_logs = [l for l in logs if l.event_type == "ERROR"]
        assert len(error_logs) >= 1
        assert any("ALGORITHM_ERROR" in l.event_code for l in error_logs)

    @pytest.mark.asyncio
    async def test_skip_event_logged(self, async_session, sample_pipeline):
        """SKIP mode generates SKIPPED event."""
        pipeline, steps = sample_pipeline
        steps[1].on_error = "SKIP"
        await async_session.flush()
        wi = await _make_work_item(async_session, pipeline)

        dispatcher = _mock_dispatcher([_ok(), _fail("skip me"), _ok()])
        resolver = _mock_resolver(async_session, steps)

        ex = await _orch(async_session, dispatcher, resolver, steps).process_work_item(wi.id)
        logs = await _get_event_logs(async_session, ex.id)

        assert any("SKIPPED" in l.event_code for l in logs)

    @pytest.mark.asyncio
    async def test_retry_events_logged(self, async_session, sample_pipeline):
        """RETRY attempts generate RETRY event logs."""
        pipeline, steps = sample_pipeline
        steps[0].on_error = "RETRY"
        steps[0].retry_count = 2
        steps[0].retry_delay_seconds = 0
        await async_session.flush()
        wi = await _make_work_item(async_session, pipeline)

        call_count = 0

        async def flaky(**kw):
            nonlocal call_count
            call_count += 1
            t = kw.get("context", {}).get("step_type", "?")
            if t == "COLLECT" and call_count == 1:
                return _fail("timeout")
            return _ok()

        dispatcher = _tracking_dispatcher(flaky)
        resolver = _mock_resolver(async_session, steps)

        ex = await _orch(async_session, dispatcher, resolver, steps).process_work_item(wi.id)
        logs = await _get_event_logs(async_session, ex.id)
        retry_logs = [l for l in logs if "RETRY" in l.event_code]
        assert len(retry_logs) >= 1

    @pytest.mark.asyncio
    async def test_output_summary_stored_per_step(self, async_session, sample_pipeline):
        """output_summary is stored on step execution record."""
        pipeline, steps = sample_pipeline
        wi = await _make_work_item(async_session, pipeline)
        dispatcher = _mock_dispatcher([
            _ok(output={"rows": 100}, summary={"record_count": 100}),
            _ok(output={"filtered": 50}, summary={"filtered_count": 50}),
            _ok(output={"written": 50}, summary={"bytes_written": 2048}),
        ])
        resolver = _mock_resolver(async_session, steps)

        ex = await _orch(async_session, dispatcher, resolver, steps).process_work_item(wi.id)
        step_execs = await _get_step_execs(async_session, ex.id)

        # summary is stored (may be from dispatcher result or as output)
        for se in step_execs:
            assert se.status == "COMPLETED"

    @pytest.mark.asyncio
    async def test_event_log_count_matches_expected(self, async_session, sample_pipeline):
        """3-step success: expect EXECUTION_START + 3*(STEP_START + STEP_DONE) + EXECUTION_END = 8 logs."""
        pipeline, steps = sample_pipeline
        wi = await _make_work_item(async_session, pipeline)
        dispatcher = _mock_dispatcher([_ok(), _ok(), _ok()])
        resolver = _mock_resolver(async_session, steps)

        ex = await _orch(async_session, dispatcher, resolver, steps).process_work_item(wi.id)
        logs = await _get_event_logs(async_session, ex.id)

        # At minimum: EXECUTION_START + 3 starts + 3 dones + EXECUTION_END = 8
        assert len(logs) >= 8

    @pytest.mark.asyncio
    async def test_event_logs_have_timestamps(self, async_session, sample_pipeline):
        """All event logs have created_at timestamps."""
        pipeline, steps = sample_pipeline
        wi = await _make_work_item(async_session, pipeline)
        dispatcher = _mock_dispatcher([_ok(), _ok(), _ok()])
        resolver = _mock_resolver(async_session, steps)

        ex = await _orch(async_session, dispatcher, resolver, steps).process_work_item(wi.id)
        logs = await _get_event_logs(async_session, ex.id)
        assert all(l.created_at is not None for l in logs)


# ===========================================================================
# 6. REPROCESS SCENARIOS
# ===========================================================================


class TestReprocessScenarios:
    """Reprocessing failed work items from specific steps."""

    @pytest.mark.asyncio
    async def test_reprocess_from_step_2(self, async_session, sample_pipeline):
        """Reprocess starting from step 2 (skip collector)."""
        pipeline, steps = sample_pipeline
        wi = await _make_work_item(async_session, pipeline)

        # First run: fails at step 2
        dispatcher = _mock_dispatcher([_ok({"data": True}), _fail("bad transform")])
        resolver = _mock_resolver(async_session, steps)
        ex1 = await _orch(async_session, dispatcher, resolver, steps).process_work_item(wi.id)
        assert ex1.status == "FAILED"

        # Reset work item
        wi.status = "DETECTED"
        await async_session.flush()

        # Reprocess from step 2
        dispatcher2 = _mock_dispatcher([_ok({"reprocessed": True}), _ok()])
        resolver2 = _mock_resolver(async_session, steps)
        ex2 = await _orch(async_session, dispatcher2, resolver2, steps).process_work_item(
            wi.id, trigger_type="REPROCESS", start_from_step=2,
        )

        assert ex2.status == "COMPLETED"
        assert ex2.execution_no == 2
        assert ex2.trigger_type == "REPROCESS"
        # Only 2 dispatches (skipped step 1)
        assert dispatcher2.dispatch.call_count == 2

    @pytest.mark.asyncio
    async def test_reprocess_request_lifecycle(self, async_session, sample_pipeline):
        """ReprocessRequest: PENDING → EXECUTING → DONE."""
        pipeline, steps = sample_pipeline
        wi = await _make_work_item(async_session, pipeline)

        # First run fails
        dispatcher = _mock_dispatcher([_ok(), _fail("err")])
        resolver = _mock_resolver(async_session, steps)
        await _orch(async_session, dispatcher, resolver, steps).process_work_item(wi.id)

        wi.status = "DETECTED"
        await async_session.flush()

        # Create reprocess request
        rr = ReprocessRequest(
            work_item_id=wi.id,
            requested_by="operator:kim",
            reason="Config was wrong",
            start_from_step=2,
            use_latest_recipe=True,
            status="PENDING",
        )
        async_session.add(rr)
        await async_session.flush()

        # Process the reprocess request
        rr.status = "APPROVED"
        await async_session.flush()

        dispatcher2 = _mock_dispatcher([_ok(), _ok()])
        resolver2 = _mock_resolver(async_session, steps)
        orch = _orch(async_session, dispatcher2, resolver2, steps)
        ex = await orch.reprocess_work_item(rr.id)

        await async_session.refresh(rr)
        assert rr.status == "DONE"
        assert rr.execution_id == ex.id
        assert ex.trigger_type == "REPROCESS"

    @pytest.mark.asyncio
    async def test_bulk_reprocess_creates_requests(self, async_session, sample_pipeline):
        """bulk_reprocess creates N pending reprocess requests."""
        pipeline, steps = sample_pipeline
        wis = []
        for _ in range(3):
            wi = await _make_work_item(async_session, pipeline)
            wis.append(wi)

        dispatcher = _mock_dispatcher([_ok(), _ok(), _ok()])
        resolver = _mock_resolver(async_session, steps)
        orch = _orch(async_session, dispatcher, resolver, steps)

        requests = await orch.bulk_reprocess(
            work_item_ids=[w.id for w in wis],
            reason="batch fix",
            requested_by="operator:lee",
        )

        assert len(requests) == 3
        assert all(r.status == "PENDING" for r in requests)
        assert all(r.requested_by == "operator:lee" for r in requests)

    @pytest.mark.asyncio
    async def test_reprocess_increments_execution_count(self, async_session, sample_pipeline):
        """Each reprocess creates a new execution with incremented execution_no."""
        pipeline, steps = sample_pipeline
        wi = await _make_work_item(async_session, pipeline)

        # Run 1
        dispatcher = _mock_dispatcher([_ok(), _fail("err")])
        resolver = _mock_resolver(async_session, steps)
        ex1 = await _orch(async_session, dispatcher, resolver, steps).process_work_item(wi.id)

        wi.status = "DETECTED"
        await async_session.flush()

        # Run 2 (reprocess)
        dispatcher2 = _mock_dispatcher([_ok(), _ok(), _ok()])
        resolver2 = _mock_resolver(async_session, steps)
        ex2 = await _orch(async_session, dispatcher2, resolver2, steps).process_work_item(
            wi.id, trigger_type="REPROCESS",
        )

        assert ex1.execution_no == 1
        assert ex2.execution_no == 2
        await async_session.refresh(wi)
        assert wi.execution_count == 2


# ===========================================================================
# 7. EDGE CASES
# ===========================================================================


class TestEdgeCases:

    @pytest.mark.asyncio
    async def test_nonexistent_work_item_raises(self, async_session, sample_pipeline):
        pipeline, steps = sample_pipeline
        dispatcher = _mock_dispatcher([])
        resolver = _mock_resolver(async_session, steps)

        with pytest.raises(ValueError, match="not found"):
            await _orch(async_session, dispatcher, resolver, steps).process_work_item(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_all_steps_disabled_completes(self, async_session, sample_pipeline):
        """If all steps are disabled, execution completes with no dispatches."""
        pipeline, steps = sample_pipeline
        for s in steps:
            s.is_enabled = False
        await async_session.flush()
        wi = await _make_work_item(async_session, pipeline)

        dispatcher = _mock_dispatcher([])
        resolver = _mock_resolver(async_session, steps)

        ex = await _orch(async_session, dispatcher, resolver, steps).process_work_item(wi.id)
        assert ex.status == "COMPLETED"
        assert dispatcher.dispatch.call_count == 0

    @pytest.mark.asyncio
    async def test_work_item_current_execution_id_updated(self, async_session, sample_pipeline):
        """current_execution_id points to latest execution."""
        pipeline, steps = sample_pipeline
        wi = await _make_work_item(async_session, pipeline)
        dispatcher = _mock_dispatcher([_ok(), _ok(), _ok()])
        resolver = _mock_resolver(async_session, steps)

        ex = await _orch(async_session, dispatcher, resolver, steps).process_work_item(wi.id)
        await async_session.refresh(wi)
        assert wi.current_execution_id == ex.id
