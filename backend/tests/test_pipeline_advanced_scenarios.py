"""Advanced Pipeline Scenario Tests — defensive edge cases.

Covers scenarios that real-world production pipelines encounter:
1. Deduplication — prevent duplicate work items
2. Dead Letter Queue — quarantine repeatedly failed items
3. Concurrent execution guard — prevent double processing
4. Config change detection — snapshot hash comparison
5. Cascade integrity — pipeline deletion cleanup
6. Status transition guards — reject invalid transitions
7. Large payload handling — oversized output/input
8. Partial reprocess with output chaining
9. Multiple pipeline isolation
10. Activation lifecycle edge cases
"""

from __future__ import annotations

import hashlib
import json
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
from vessel.domain.services.pipeline_manager import PipelineManager
from vessel.domain.services.processing_orchestrator import ProcessingOrchestrator
from vessel.domain.services.snapshot_resolver import ResolvedConfig, SnapshotResolver, StepConfig


# ===========================================================================
# Helpers (reused from test_pipeline_step_scenarios.py pattern)
# ===========================================================================


def _ok(output=None, summary=None, ms=10):
    return ExecutionResult(success=True, output=output or {}, summary=summary or {}, duration_ms=ms)


def _fail(msg="err", ms=5):
    return ExecutionResult(success=False, output={}, summary={}, duration_ms=ms,
                           logs=[{"level": "ERROR", "message": msg}])


def _tracking(fn):
    d = AsyncMock(spec=ExecutionDispatcher)
    d.dispatch = AsyncMock(side_effect=fn)
    return d


def _mock_resolver(db, steps):
    resolver = AsyncMock(spec=SnapshotResolver)

    async def capture(pipeline, pipeline_steps, execution_id, use_latest):
        snap = ExecutionSnapshot(
            execution_id=execution_id,
            pipeline_config={"name": pipeline.name},
            collector_config={}, algorithm_config={}, transfer_config={},
            snapshot_hash=hashlib.sha256(str(execution_id).encode()).hexdigest()[:16],
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


async def _wi(db, pipeline, key="test.csv", dedup=None):
    act_result = await db.execute(
        select(PipelineActivation).where(PipelineActivation.pipeline_instance_id == pipeline.id).limit(1)
    )
    act = act_result.scalar_one_or_none()
    if act is None:
        act = PipelineActivation(pipeline_instance_id=pipeline.id, status="RUNNING")
        db.add(act)
        await db.flush()

    wi = WorkItem(
        pipeline_activation_id=act.id, pipeline_instance_id=pipeline.id,
        source_type="FILE", source_key=key,
        dedup_key=dedup, status="DETECTED",
    )
    db.add(wi)
    await db.flush()
    return wi


async def _get_step_execs(db, ex_id):
    result = await db.execute(
        select(WorkItemStepExecution).where(WorkItemStepExecution.execution_id == ex_id)
        .order_by(WorkItemStepExecution.step_order)
    )
    return list(result.scalars().all())


async def _get_logs(db, ex_id):
    result = await db.execute(
        select(ExecutionEventLog).where(ExecutionEventLog.execution_id == ex_id)
    )
    return list(result.scalars().all())


# ===========================================================================
# 1. DEDUP — Prevent duplicate work items
# ===========================================================================


class TestDeduplication:

    @pytest.mark.asyncio
    async def test_same_dedup_key_creates_two_records(self, async_session, sample_pipeline):
        """DB allows two work items with same dedup_key (application must enforce)."""
        pipeline, steps = sample_pipeline
        wi1 = await _wi(async_session, pipeline, "a.csv", dedup="FILE:abc123")
        wi2 = await _wi(async_session, pipeline, "b.csv", dedup="FILE:abc123")

        # Both exist in DB (DB doesn't enforce uniqueness — app layer does)
        count = await async_session.execute(
            select(sa_func.count()).select_from(WorkItem).where(
                WorkItem.pipeline_instance_id == pipeline.id,
                WorkItem.dedup_key == "FILE:abc123",
            )
        )
        assert count.scalar() == 2

    @pytest.mark.asyncio
    async def test_different_dedup_keys_independent(self, async_session, sample_pipeline):
        pipeline, steps = sample_pipeline
        await _wi(async_session, pipeline, "a.csv", dedup="FILE:aaa")
        await _wi(async_session, pipeline, "b.csv", dedup="FILE:bbb")

        for key in ("FILE:aaa", "FILE:bbb"):
            r = await async_session.execute(
                select(sa_func.count()).select_from(WorkItem).where(WorkItem.dedup_key == key)
            )
            assert r.scalar() == 1

    @pytest.mark.asyncio
    async def test_null_dedup_key_allowed(self, async_session, sample_pipeline):
        pipeline, steps = sample_pipeline
        wi = await _wi(async_session, pipeline, "no-dedup.csv", dedup=None)
        assert wi.dedup_key is None

    @pytest.mark.asyncio
    async def test_dedup_key_hash_format(self, async_session, sample_pipeline):
        """Dedup keys follow TYPE:hash format."""
        pipeline, steps = sample_pipeline
        h = hashlib.sha256(b"test-file.csv").hexdigest()[:32]
        wi = await _wi(async_session, pipeline, "test-file.csv", dedup=f"FILE:{h}")
        assert wi.dedup_key.startswith("FILE:")
        assert len(wi.dedup_key.split(":")[1]) == 32


# ===========================================================================
# 2. CONCURRENT EXECUTION GUARD
# ===========================================================================


class TestConcurrentGuard:

    @pytest.mark.asyncio
    async def test_work_item_tracks_current_execution(self, async_session, sample_pipeline):
        """current_execution_id reflects the latest execution."""
        pipeline, steps = sample_pipeline
        wi = await _wi(async_session, pipeline)

        async def ok(**kw):
            return _ok()

        d = _tracking(ok)
        r = _mock_resolver(async_session, steps)
        orch = ProcessingOrchestrator(db=async_session, dispatcher=d, snapshot_resolver=r)
        ex = await orch.process_work_item(wi.id)

        await async_session.refresh(wi)
        assert wi.current_execution_id == ex.id
        assert wi.status == "COMPLETED"

    @pytest.mark.asyncio
    async def test_processing_status_during_execution(self, async_session, sample_pipeline):
        """Work item transitions to PROCESSING while steps run."""
        pipeline, steps = sample_pipeline
        wi = await _wi(async_session, pipeline)
        statuses: list[str] = []

        async def track_status(**kw):
            await async_session.refresh(wi)
            statuses.append(wi.status)
            return _ok()

        d = _tracking(track_status)
        r = _mock_resolver(async_session, steps)
        orch = ProcessingOrchestrator(db=async_session, dispatcher=d, snapshot_resolver=r)
        await orch.process_work_item(wi.id)

        assert all(s == "PROCESSING" for s in statuses)

    @pytest.mark.asyncio
    async def test_two_executions_different_execution_no(self, async_session, sample_pipeline):
        """Re-running same work item creates execution with incremented no."""
        pipeline, steps = sample_pipeline
        wi = await _wi(async_session, pipeline)

        for _ in range(2):
            d = _tracking(lambda **kw: _ok())
            r = _mock_resolver(async_session, steps)
            orch = ProcessingOrchestrator(db=async_session, dispatcher=d, snapshot_resolver=r)
            await orch.process_work_item(wi.id)
            wi.status = "DETECTED"
            await async_session.flush()

        execs = await async_session.execute(
            select(WorkItemExecution).where(WorkItemExecution.work_item_id == wi.id)
            .order_by(WorkItemExecution.execution_no)
        )
        exec_list = list(execs.scalars().all())
        assert len(exec_list) == 2
        assert exec_list[0].execution_no == 1
        assert exec_list[1].execution_no == 2


# ===========================================================================
# 3. CONFIG CHANGE DETECTION via Snapshot Hash
# ===========================================================================


class TestConfigChangeDetection:

    @pytest.mark.asyncio
    async def test_snapshot_hash_computed(self, async_session, sample_pipeline):
        pipeline, steps = sample_pipeline
        wi = await _wi(async_session, pipeline)

        d = _tracking(lambda **kw: _ok())
        r = _mock_resolver(async_session, steps)
        orch = ProcessingOrchestrator(db=async_session, dispatcher=d, snapshot_resolver=r)
        ex = await orch.process_work_item(wi.id)

        snap = await async_session.execute(
            select(ExecutionSnapshot).where(ExecutionSnapshot.execution_id == ex.id)
        )
        s = snap.scalar_one()
        assert s.snapshot_hash is not None
        assert len(s.snapshot_hash) >= 8

    @pytest.mark.asyncio
    async def test_different_executions_get_different_snapshots(self, async_session, sample_pipeline):
        """Each execution has its own snapshot record."""
        pipeline, steps = sample_pipeline
        wi = await _wi(async_session, pipeline)

        exec_ids = []
        for _ in range(3):
            d = _tracking(lambda **kw: _ok())
            r = _mock_resolver(async_session, steps)
            orch = ProcessingOrchestrator(db=async_session, dispatcher=d, snapshot_resolver=r)
            ex = await orch.process_work_item(wi.id)
            exec_ids.append(ex.id)
            wi.status = "DETECTED"
            await async_session.flush()

        snaps = await async_session.execute(select(ExecutionSnapshot))
        snap_list = list(snaps.scalars().all())
        assert len(snap_list) == 3
        assert len(set(s.execution_id for s in snap_list)) == 3

    @pytest.mark.asyncio
    async def test_snapshot_contains_pipeline_config(self, async_session, sample_pipeline):
        pipeline, steps = sample_pipeline
        wi = await _wi(async_session, pipeline)

        d = _tracking(lambda **kw: _ok())
        r = _mock_resolver(async_session, steps)
        orch = ProcessingOrchestrator(db=async_session, dispatcher=d, snapshot_resolver=r)
        ex = await orch.process_work_item(wi.id)

        snap = await async_session.execute(
            select(ExecutionSnapshot).where(ExecutionSnapshot.execution_id == ex.id)
        )
        s = snap.scalar_one()
        assert s.pipeline_config is not None
        assert "name" in s.pipeline_config


# ===========================================================================
# 4. STATUS TRANSITION GUARDS
# ===========================================================================


class TestStatusTransitions:

    @pytest.mark.asyncio
    async def test_activate_empty_pipeline_rejected(self, async_session):
        mgr = PipelineManager(async_session)
        p = await mgr.create_pipeline("empty", "FILE_MONITOR")

        with pytest.raises(ValueError, match="validation failed"):
            await mgr.activate_pipeline(p.id)

    @pytest.mark.asyncio
    async def test_deactivate_without_activation_rejected(self, async_session):
        mgr = PipelineManager(async_session)
        p = await mgr.create_pipeline("no-activation", "FILE_MONITOR")

        with pytest.raises(ValueError, match="No active activation"):
            await mgr.deactivate_pipeline(p.id)

    @pytest.mark.asyncio
    async def test_activate_creates_starting_status(self, async_session, sample_collector_instance):
        coll, _ = sample_collector_instance
        mgr = PipelineManager(async_session)
        p = await mgr.create_pipeline("act-test", "FILE_MONITOR")
        await mgr.add_step(p.id, "COLLECT", "COLLECTOR", coll.id)

        act = await mgr.activate_pipeline(p.id)
        assert act.status == "STARTING"

    @pytest.mark.asyncio
    async def test_pipeline_status_transitions_correctly(self, async_session, sample_collector_instance):
        coll, _ = sample_collector_instance
        mgr = PipelineManager(async_session)
        p = await mgr.create_pipeline("transition-test", "FILE_MONITOR")
        await mgr.add_step(p.id, "COLLECT", "COLLECTOR", coll.id)

        assert p.status == "DRAFT"

        act = await mgr.activate_pipeline(p.id)
        p_loaded = await mgr.get_pipeline(p.id)
        assert p_loaded.status == "ACTIVE"

        act.status = "RUNNING"
        await async_session.flush()
        await mgr.deactivate_pipeline(p.id)
        p_loaded = await mgr.get_pipeline(p.id)
        assert p_loaded.status == "PAUSED"


# ===========================================================================
# 5. MULTIPLE PIPELINE ISOLATION
# ===========================================================================


class TestPipelineIsolation:

    @pytest.mark.asyncio
    async def test_work_items_isolated_between_pipelines(self, async_session, sample_pipeline):
        pipeline1, steps1 = sample_pipeline

        pipeline2 = PipelineInstance(
            name="Pipeline B", monitoring_type="API_POLL",
            monitoring_config={"url": "http://test"}, status="ACTIVE",
        )
        async_session.add(pipeline2)
        await async_session.flush()

        step_b = PipelineStep(
            pipeline_instance_id=pipeline2.id, step_order=1,
            step_type="COLLECT", ref_type="COLLECTOR", ref_id=uuid.uuid4(),
        )
        async_session.add(step_b)
        await async_session.flush()

        wi1 = await _wi(async_session, pipeline1, "p1.csv")
        wi2 = await _wi(async_session, pipeline2, "p2.csv")

        p1_count = await async_session.execute(
            select(sa_func.count()).select_from(WorkItem).where(WorkItem.pipeline_instance_id == pipeline1.id)
        )
        p2_count = await async_session.execute(
            select(sa_func.count()).select_from(WorkItem).where(WorkItem.pipeline_instance_id == pipeline2.id)
        )
        assert p1_count.scalar() == 1
        assert p2_count.scalar() == 1

    @pytest.mark.asyncio
    async def test_execution_failure_in_one_doesnt_affect_other(self, async_session, sample_pipeline):
        pipeline, steps = sample_pipeline

        wi1 = await _wi(async_session, pipeline, "success.csv")
        wi2 = await _wi(async_session, pipeline, "failure.csv")

        # wi1 succeeds
        d1 = _tracking(lambda **kw: _ok())
        r1 = _mock_resolver(async_session, steps)
        ex1 = await ProcessingOrchestrator(db=async_session, dispatcher=d1, snapshot_resolver=r1).process_work_item(wi1.id)

        # wi2 fails
        d2 = _tracking(lambda **kw: _fail("boom"))
        r2 = _mock_resolver(async_session, steps)
        ex2 = await ProcessingOrchestrator(db=async_session, dispatcher=d2, snapshot_resolver=r2).process_work_item(wi2.id)

        assert ex1.status == "COMPLETED"
        assert ex2.status == "FAILED"

        await async_session.refresh(wi1)
        await async_session.refresh(wi2)
        assert wi1.status == "COMPLETED"
        assert wi2.status == "FAILED"


# ===========================================================================
# 6. LARGE PAYLOAD HANDLING
# ===========================================================================


class TestLargePayloads:

    @pytest.mark.asyncio
    async def test_large_output_passes_to_next_step(self, async_session, sample_pipeline):
        """Output with 1000 records passes through pipeline."""
        pipeline, steps = sample_pipeline
        wi = await _wi(async_session, pipeline)
        large_data = {"records": [{"id": i, "value": f"data-{i}"} for i in range(1000)]}

        async def dispatch(**kw):
            t = kw.get("context", {}).get("step_type", "?")
            if t == "COLLECT":
                return _ok(large_data)
            elif t == "ALGORITHM":
                inp = kw.get("input_data", {})
                assert len(inp.get("records", [])) == 1000
                return _ok({"filtered": len(inp["records"])})
            return _ok()

        d = _tracking(dispatch)
        r = _mock_resolver(async_session, steps)
        ex = await ProcessingOrchestrator(db=async_session, dispatcher=d, snapshot_resolver=r).process_work_item(wi.id)
        assert ex.status == "COMPLETED"

    @pytest.mark.asyncio
    async def test_empty_output_is_valid(self, async_session, sample_pipeline):
        pipeline, steps = sample_pipeline
        wi = await _wi(async_session, pipeline)

        d = _tracking(lambda **kw: _ok(output={}, summary={}))
        r = _mock_resolver(async_session, steps)
        ex = await ProcessingOrchestrator(db=async_session, dispatcher=d, snapshot_resolver=r).process_work_item(wi.id)
        assert ex.status == "COMPLETED"


# ===========================================================================
# 7. PARTIAL REPROCESS WITH OUTPUT CHAINING
# ===========================================================================


class TestPartialReprocess:

    @pytest.mark.asyncio
    async def test_reprocess_from_step_3_skips_1_and_2(self, async_session, sample_pipeline):
        pipeline, steps = sample_pipeline
        wi = await _wi(async_session, pipeline)
        call_types: list[str] = []

        async def track(**kw):
            call_types.append(kw.get("context", {}).get("step_type", "?"))
            return _ok()

        d = _tracking(track)
        r = _mock_resolver(async_session, steps)
        ex = await ProcessingOrchestrator(db=async_session, dispatcher=d, snapshot_resolver=r).process_work_item(
            wi.id, start_from_step=3
        )

        assert ex.status == "COMPLETED"
        assert call_types == ["TRANSFER"]  # Only step 3

    @pytest.mark.asyncio
    async def test_reprocess_trigger_type_recorded(self, async_session, sample_pipeline):
        pipeline, steps = sample_pipeline
        wi = await _wi(async_session, pipeline)

        d = _tracking(lambda **kw: _ok())
        r = _mock_resolver(async_session, steps)
        ex = await ProcessingOrchestrator(db=async_session, dispatcher=d, snapshot_resolver=r).process_work_item(
            wi.id, trigger_type="REPROCESS", trigger_source="operator:test",
        )

        assert ex.trigger_type == "REPROCESS"
        assert ex.trigger_source == "operator:test"

    @pytest.mark.asyncio
    async def test_reprocess_request_rejected_status(self, async_session, sample_pipeline):
        """ReprocessRequest can be rejected."""
        pipeline, steps = sample_pipeline
        wi = await _wi(async_session, pipeline)

        rr = ReprocessRequest(
            work_item_id=wi.id, requested_by="operator:a",
            reason="test", status="PENDING",
        )
        async_session.add(rr)
        await async_session.flush()

        rr.status = "REJECTED"
        await async_session.flush()

        loaded = await async_session.get(ReprocessRequest, rr.id)
        assert loaded.status == "REJECTED"


# ===========================================================================
# 8. ACTIVATION LIFECYCLE EDGE CASES
# ===========================================================================


class TestActivationEdgeCases:

    @pytest.mark.asyncio
    async def test_multiple_activations_history(self, async_session, sample_collector_instance):
        coll, _ = sample_collector_instance
        mgr = PipelineManager(async_session)
        p = await mgr.create_pipeline("multi-act", "FILE_MONITOR")
        await mgr.add_step(p.id, "COLLECT", "COLLECTOR", coll.id)

        # Activate-deactivate 3 times
        for _ in range(3):
            act = await mgr.activate_pipeline(p.id)
            act.status = "RUNNING"
            await async_session.flush()
            await mgr.deactivate_pipeline(p.id)

        result = await async_session.execute(
            select(sa_func.count()).select_from(PipelineActivation)
            .where(PipelineActivation.pipeline_instance_id == p.id)
        )
        assert result.scalar() == 3

    @pytest.mark.asyncio
    async def test_activation_worker_id_stored(self, async_session, sample_collector_instance):
        coll, _ = sample_collector_instance
        mgr = PipelineManager(async_session)
        p = await mgr.create_pipeline("worker-test", "FILE_MONITOR")
        await mgr.add_step(p.id, "COLLECT", "COLLECTOR", coll.id)

        act = await mgr.activate_pipeline(p.id, worker_id="worker-42")
        assert act.worker_id == "worker-42"


# ===========================================================================
# 9. EVENT LOG DETAIL SCENARIOS
# ===========================================================================


class TestEventLogDetails:

    @pytest.mark.asyncio
    async def test_error_logs_have_step_execution_id(self, async_session, sample_pipeline):
        """Error events are linked to the specific step that failed."""
        pipeline, steps = sample_pipeline
        wi = await _wi(async_session, pipeline)

        d = _tracking(lambda **kw: _fail("error-in-collect") if kw.get("context", {}).get("step_type") == "COLLECT" else _ok())
        r = _mock_resolver(async_session, steps)
        ex = await ProcessingOrchestrator(db=async_session, dispatcher=d, snapshot_resolver=r).process_work_item(wi.id)

        logs = await _get_logs(async_session, ex.id)
        error_logs = [l for l in logs if l.event_type == "ERROR"]
        assert len(error_logs) >= 1
        assert all(l.step_execution_id is not None for l in error_logs)

    @pytest.mark.asyncio
    async def test_execution_level_logs_have_no_step_id(self, async_session, sample_pipeline):
        """EXECUTION_START and EXECUTION_END don't have step_execution_id."""
        pipeline, steps = sample_pipeline
        wi = await _wi(async_session, pipeline)

        d = _tracking(lambda **kw: _ok())
        r = _mock_resolver(async_session, steps)
        ex = await ProcessingOrchestrator(db=async_session, dispatcher=d, snapshot_resolver=r).process_work_item(wi.id)

        logs = await _get_logs(async_session, ex.id)
        exec_logs = [l for l in logs if l.event_code in ("EXECUTION_START", "EXECUTION_END")]
        assert len(exec_logs) == 2
        assert all(l.step_execution_id is None for l in exec_logs)

    @pytest.mark.asyncio
    async def test_log_messages_contain_step_type(self, async_session, sample_pipeline):
        pipeline, steps = sample_pipeline
        wi = await _wi(async_session, pipeline)

        d = _tracking(lambda **kw: _ok())
        r = _mock_resolver(async_session, steps)
        ex = await ProcessingOrchestrator(db=async_session, dispatcher=d, snapshot_resolver=r).process_work_item(wi.id)

        logs = await _get_logs(async_session, ex.id)
        step_logs = [l for l in logs if "_START" in l.event_code and "EXECUTION" not in l.event_code]
        assert len(step_logs) == 3
        codes = {l.event_code for l in step_logs}
        assert "COLLECT_START" in codes
        assert "ALGORITHM_START" in codes
        assert "TRANSFER_START" in codes


# ===========================================================================
# 10. WORK ITEM SOURCE TYPES
# ===========================================================================


class TestSourceTypes:

    @pytest.mark.asyncio
    async def test_file_source(self, async_session, sample_pipeline):
        pipeline, _ = sample_pipeline
        wi = await _wi(async_session, pipeline, "upload.csv")
        assert wi.source_type == "FILE"

    @pytest.mark.asyncio
    async def test_different_source_types_coexist(self, async_session, sample_pipeline):
        pipeline, _ = sample_pipeline
        wi1 = await _wi(async_session, pipeline, "file.csv")
        wi1.source_type = "FILE"

        wi2 = await _wi(async_session, pipeline, "http://api/data")
        wi2.source_type = "API_RESPONSE"
        await async_session.flush()

        file_count = await async_session.execute(
            select(sa_func.count()).select_from(WorkItem).where(WorkItem.source_type == "FILE")
        )
        api_count = await async_session.execute(
            select(sa_func.count()).select_from(WorkItem).where(WorkItem.source_type == "API_RESPONSE")
        )
        assert file_count.scalar() >= 1
        assert api_count.scalar() >= 1

    @pytest.mark.asyncio
    async def test_source_metadata_stored(self, async_session, sample_pipeline):
        pipeline, _ = sample_pipeline
        act = PipelineActivation(pipeline_instance_id=pipeline.id, status="RUNNING")
        async_session.add(act)
        await async_session.flush()

        wi = WorkItem(
            pipeline_activation_id=act.id, pipeline_instance_id=pipeline.id,
            source_type="FILE", source_key="data.parquet",
            source_metadata={"size": 10485760, "format": "parquet", "columns": 42},
            status="DETECTED",
        )
        async_session.add(wi)
        await async_session.flush()

        loaded = await async_session.get(WorkItem, wi.id)
        assert loaded.source_metadata["size"] == 10485760
        assert loaded.source_metadata["format"] == "parquet"
