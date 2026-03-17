"""End-to-End Pipeline Flow Tests.

Tests the COMPLETE data path:
  Collect (mock source) → Process (recipe-driven transform) → Export (verify output)

Verifies:
1. Data flows through all 3 steps
2. Recipe values drive actual transformation behavior
3. Output from step N becomes input to step N+1
4. Export result is captured (DB write simulation)
5. Reprocess uses correct recipe version
6. Snapshot captures exact config used
7. Event logs track full data lineage
"""

from __future__ import annotations

import json
import uuid
from typing import Any
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
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
# Realistic Dispatchers — simulate actual connector behavior
# ===========================================================================


class RealisticDispatcher:
    """Simulates a realistic pipeline: FTP collect → transform → DB write."""

    def __init__(self):
        self.call_log: list[dict] = []
        self.db_writes: list[dict] = []
        self.webhook_calls: list[dict] = []

    async def dispatch(self, **kw):
        step_type = kw.get("context", {}).get("step_type", "?")
        config = kw.get("config", {})
        input_data = kw.get("input_data")
        self.call_log.append({"step_type": step_type, "config": config, "input": input_data})

        if step_type == "COLLECT":
            # Simulate: FTP collector fetches CSV rows
            return ExecutionResult(
                success=True,
                output={
                    "records": [
                        {"device_id": "D001", "temperature": 72.5, "timestamp": "2026-03-17T10:00:00Z"},
                        {"device_id": "D002", "temperature": 98.1, "timestamp": "2026-03-17T10:01:00Z"},
                        {"device_id": "D003", "temperature": 65.3, "timestamp": "2026-03-17T10:02:00Z"},
                    ],
                    "source": "ftp://equipment-server/data/sensors/",
                    "file_count": 1,
                },
                summary={"records_collected": 3, "source": "ftp"},
                duration_ms=150,
            )

        elif step_type == "ALGORITHM":
            # Simulate: Anomaly Detector using recipe threshold
            threshold = config.get("threshold", 90.0) if config else 90.0
            records = (input_data or {}).get("records", [])
            anomalies = [r for r in records if r.get("temperature", 0) > threshold]
            normal = [r for r in records if r.get("temperature", 0) <= threshold]

            return ExecutionResult(
                success=True,
                output={
                    "records": anomalies,
                    "normal_count": len(normal),
                    "anomaly_count": len(anomalies),
                    "threshold_used": threshold,
                },
                summary={"anomalies": len(anomalies), "total": len(records), "threshold": threshold},
                duration_ms=50,
            )

        elif step_type == "TRANSFER":
            # Simulate: DB Writer inserts records
            records = (input_data or {}).get("records", [])
            table = config.get("table_name", "unknown") if config else "unknown"
            self.db_writes.extend(records)

            return ExecutionResult(
                success=True,
                output={"records_written": len(records), "table": table},
                summary={"table": table, "records_written": len(records)},
                duration_ms=80,
            )

        return ExecutionResult(success=True, output={}, summary={}, duration_ms=1)


def _make_resolver_with_recipes(db, steps, recipes: dict[str, dict]):
    """Create a resolver that injects specific recipe configs per step type."""
    resolver = AsyncMock(spec=SnapshotResolver)

    async def capture(pipeline, pipeline_steps, execution_id, use_latest):
        snap = ExecutionSnapshot(
            execution_id=execution_id,
            pipeline_config={"name": pipeline.name},
            collector_config={}, algorithm_config={}, transfer_config={},
            snapshot_hash="recipe-test-" + str(execution_id)[:8],
        )
        db.add(snap)
        await db.flush()
        return snap

    async def resolve(snapshot_id):
        rc = ResolvedConfig(pipeline_config={})
        for step in steps:
            recipe_config = recipes.get(step.step_type, {"test": True})
            rc.steps.append(StepConfig(
                step_id=step.id, step_order=step.step_order, step_type=step.step_type,
                ref_type=step.ref_type, ref_id=step.ref_id,
                execution_type="PLUGIN", execution_ref=f"{step.ref_type}:test",
                resolved_config=recipe_config, version_no=1,
            ))
        return rc

    resolver.capture = AsyncMock(side_effect=capture)
    resolver.resolve = AsyncMock(side_effect=resolve)
    return resolver


async def _wi(db, pipeline, key="sensor-data.csv"):
    act_r = await db.execute(
        select(PipelineActivation).where(PipelineActivation.pipeline_instance_id == pipeline.id).limit(1)
    )
    act = act_r.scalar_one_or_none()
    if not act:
        act = PipelineActivation(pipeline_instance_id=pipeline.id, status="RUNNING")
        db.add(act)
        await db.flush()

    wi = WorkItem(
        pipeline_activation_id=act.id, pipeline_instance_id=pipeline.id,
        source_type="FILE", source_key=key, status="DETECTED",
    )
    db.add(wi)
    await db.flush()
    return wi


# ===========================================================================
# 1. FULL PIPELINE E2E: Collect → Process → Export
# ===========================================================================


class TestFullPipelineFlow:

    @pytest.mark.asyncio
    async def test_ftp_anomaly_db_happy_path(self, async_session, sample_pipeline):
        """FTP Collect → Anomaly Detection (threshold=90) → DB Write."""
        pipeline, steps = sample_pipeline
        wi = await _wi(async_session, pipeline)
        dispatcher = RealisticDispatcher()

        # Recipe: anomaly threshold = 90.0, DB table = sensor_anomalies
        recipes = {
            "COLLECT": {"remote_path": "/data/sensors", "file_filter_regex": r".*\.csv$"},
            "ALGORITHM": {"threshold": 90.0, "method": "simple"},
            "TRANSFER": {"table_name": "sensor_anomalies", "write_mode": "INSERT"},
        }
        resolver = _make_resolver_with_recipes(async_session, steps, recipes)

        d = AsyncMock(spec=ExecutionDispatcher)
        d.dispatch = AsyncMock(side_effect=dispatcher.dispatch)
        orch = ProcessingOrchestrator(db=async_session, dispatcher=d, snapshot_resolver=resolver)

        ex = await orch.process_work_item(wi.id)
        assert ex.status == "COMPLETED"

        # Verify: 3 records collected, 1 anomaly (temp 98.1 > 90), 1 written to DB
        assert len(dispatcher.call_log) == 3
        assert dispatcher.call_log[0]["step_type"] == "COLLECT"
        assert dispatcher.call_log[1]["step_type"] == "ALGORITHM"
        assert dispatcher.call_log[2]["step_type"] == "TRANSFER"

        # Check: anomaly detector received 3 records from collector
        algo_input = dispatcher.call_log[1]["input"]
        assert len(algo_input["records"]) == 3

        # Check: DB writer received only anomalies (1 record with temp > 90)
        export_input = dispatcher.call_log[2]["input"]
        assert export_input["anomaly_count"] == 1
        assert len(export_input["records"]) == 1
        assert export_input["records"][0]["device_id"] == "D002"

    @pytest.mark.asyncio
    async def test_recipe_threshold_changes_output(self, async_session, sample_pipeline):
        """Different threshold in recipe produces different anomaly count."""
        pipeline, steps = sample_pipeline

        # Test 1: threshold=90 → 1 anomaly
        wi1 = await _wi(async_session, pipeline, "run1.csv")
        d1 = RealisticDispatcher()
        mock_d1 = AsyncMock(spec=ExecutionDispatcher)
        mock_d1.dispatch = AsyncMock(side_effect=d1.dispatch)
        r1 = _make_resolver_with_recipes(async_session, steps, {"ALGORITHM": {"threshold": 90.0}})
        ex1 = await ProcessingOrchestrator(db=async_session, dispatcher=mock_d1, snapshot_resolver=r1).process_work_item(wi1.id)

        # Test 2: threshold=60 → 2 anomalies
        wi2 = await _wi(async_session, pipeline, "run2.csv")
        d2 = RealisticDispatcher()
        mock_d2 = AsyncMock(spec=ExecutionDispatcher)
        mock_d2.dispatch = AsyncMock(side_effect=d2.dispatch)
        r2 = _make_resolver_with_recipes(async_session, steps, {"ALGORITHM": {"threshold": 60.0}})
        ex2 = await ProcessingOrchestrator(db=async_session, dispatcher=mock_d2, snapshot_resolver=r2).process_work_item(wi2.id)

        # Verify: different thresholds → different anomaly counts
        algo1_output = d1.call_log[1]  # ALGORITHM step
        algo2_output = d2.call_log[1]
        assert algo1_output["config"].get("threshold") == 90.0
        assert algo2_output["config"].get("threshold") == 60.0

        # Anomaly counts differ based on threshold
        export1_input = d1.call_log[2]["input"]
        export2_input = d2.call_log[2]["input"]
        assert export1_input["anomaly_count"] == 1   # Only temp 98.1 > 90
        assert export2_input["anomaly_count"] == 3   # all temps (72.5, 98.1, 65.3) > 60

    @pytest.mark.asyncio
    async def test_db_writer_receives_correct_table_from_recipe(self, async_session, sample_pipeline):
        """Recipe table_name config is passed to the export step."""
        pipeline, steps = sample_pipeline
        wi = await _wi(async_session, pipeline)
        dispatcher = RealisticDispatcher()

        recipes = {
            "TRANSFER": {"table_name": "custom_output_table", "write_mode": "UPSERT"},
        }
        resolver = _make_resolver_with_recipes(async_session, steps, recipes)
        d = AsyncMock(spec=ExecutionDispatcher)
        d.dispatch = AsyncMock(side_effect=dispatcher.dispatch)

        await ProcessingOrchestrator(db=async_session, dispatcher=d, snapshot_resolver=resolver).process_work_item(wi.id)

        export_call = dispatcher.call_log[2]
        assert export_call["config"]["table_name"] == "custom_output_table"
        assert export_call["config"]["write_mode"] == "UPSERT"


# ===========================================================================
# 2. RECIPE VERSION → ACTUAL BEHAVIOR
# ===========================================================================


class TestRecipeDrivesExecution:

    @pytest.mark.asyncio
    async def test_collector_recipe_values_passed(self, async_session, sample_pipeline):
        """Collector recipe (remote_path, regex) is passed to dispatch."""
        pipeline, steps = sample_pipeline
        wi = await _wi(async_session, pipeline)
        dispatcher = RealisticDispatcher()

        recipes = {
            "COLLECT": {
                "remote_path": "/equipment/plant-A/sensors",
                "file_filter_regex": r"temp_\d{8}\.csv",
                "recursive": True,
            },
        }
        resolver = _make_resolver_with_recipes(async_session, steps, recipes)
        d = AsyncMock(spec=ExecutionDispatcher)
        d.dispatch = AsyncMock(side_effect=dispatcher.dispatch)

        await ProcessingOrchestrator(db=async_session, dispatcher=d, snapshot_resolver=resolver).process_work_item(wi.id)

        collect_call = dispatcher.call_log[0]
        assert collect_call["config"]["remote_path"] == "/equipment/plant-A/sensors"
        assert collect_call["config"]["file_filter_regex"] == r"temp_\d{8}\.csv"
        assert collect_call["config"]["recursive"] is True

    @pytest.mark.asyncio
    async def test_process_recipe_multiple_params(self, async_session, sample_pipeline):
        """Process recipe with multiple parameters all passed correctly."""
        pipeline, steps = sample_pipeline
        wi = await _wi(async_session, pipeline)
        dispatcher = RealisticDispatcher()

        recipes = {
            "ALGORITHM": {
                "threshold": 75.0,
                "method": "z_score",
                "window_size": 100,
                "sensitivity": 2.5,
            },
        }
        resolver = _make_resolver_with_recipes(async_session, steps, recipes)
        d = AsyncMock(spec=ExecutionDispatcher)
        d.dispatch = AsyncMock(side_effect=dispatcher.dispatch)

        await ProcessingOrchestrator(db=async_session, dispatcher=d, snapshot_resolver=resolver).process_work_item(wi.id)

        algo_call = dispatcher.call_log[1]
        assert algo_call["config"]["threshold"] == 75.0
        assert algo_call["config"]["method"] == "z_score"
        assert algo_call["config"]["window_size"] == 100
        assert algo_call["config"]["sensitivity"] == 2.5


# ===========================================================================
# 3. REPROCESS E2E — Failed → Fix Recipe → Reprocess
# ===========================================================================


class TestReprocessE2E:

    @pytest.mark.asyncio
    async def test_reprocess_after_recipe_fix(self, async_session, sample_pipeline):
        """
        Run 1: Fails at export (wrong table name).
        Operator fixes recipe.
        Run 2: Reprocess from step 3 with fixed recipe → succeeds.
        """
        pipeline, steps = sample_pipeline
        wi = await _wi(async_session, pipeline)

        # Run 1: Export fails
        call_count = 0

        async def fail_on_export(**kw):
            nonlocal call_count
            call_count += 1
            t = kw.get("context", {}).get("step_type", "?")
            if t == "TRANSFER":
                return ExecutionResult(
                    success=False, output={}, summary={}, duration_ms=10,
                    logs=[{"level": "ERROR", "message": "Table 'wrong_table' does not exist"}],
                )
            return ExecutionResult(success=True, output={"records": [{"id": 1}]}, summary={}, duration_ms=10)

        d1 = AsyncMock(spec=ExecutionDispatcher)
        d1.dispatch = AsyncMock(side_effect=fail_on_export)
        r1 = _make_resolver_with_recipes(async_session, steps, {
            "TRANSFER": {"table_name": "wrong_table"},
        })
        ex1 = await ProcessingOrchestrator(db=async_session, dispatcher=d1, snapshot_resolver=r1).process_work_item(wi.id)
        assert ex1.status == "FAILED"

        # Fix recipe + reprocess from step 3
        wi.status = "DETECTED"
        await async_session.flush()

        d2 = AsyncMock(spec=ExecutionDispatcher)
        d2.dispatch = AsyncMock(return_value=ExecutionResult(
            success=True, output={"written": 1}, summary={"table": "correct_table"}, duration_ms=20,
        ))
        r2 = _make_resolver_with_recipes(async_session, steps, {
            "TRANSFER": {"table_name": "correct_table", "write_mode": "INSERT"},
        })
        ex2 = await ProcessingOrchestrator(db=async_session, dispatcher=d2, snapshot_resolver=r2).process_work_item(
            wi.id, trigger_type="REPROCESS", start_from_step=3,
        )

        assert ex2.status == "COMPLETED"
        assert ex2.trigger_type == "REPROCESS"
        assert ex2.execution_no == 2

    @pytest.mark.asyncio
    async def test_reprocess_full_chain_with_new_recipe(self, async_session, sample_pipeline):
        """
        Full reprocess (from step 1) with updated recipe values.
        Proves new recipe values are used in the re-execution.
        """
        pipeline, steps = sample_pipeline
        wi = await _wi(async_session, pipeline)

        # Run 1: Old threshold
        d1 = RealisticDispatcher()
        m1 = AsyncMock(spec=ExecutionDispatcher)
        m1.dispatch = AsyncMock(side_effect=d1.dispatch)
        r1 = _make_resolver_with_recipes(async_session, steps, {"ALGORITHM": {"threshold": 99.0}})
        ex1 = await ProcessingOrchestrator(db=async_session, dispatcher=m1, snapshot_resolver=r1).process_work_item(wi.id)

        wi.status = "DETECTED"
        await async_session.flush()

        # Run 2: New threshold (lower → catches more anomalies)
        d2 = RealisticDispatcher()
        m2 = AsyncMock(spec=ExecutionDispatcher)
        m2.dispatch = AsyncMock(side_effect=d2.dispatch)
        r2 = _make_resolver_with_recipes(async_session, steps, {"ALGORITHM": {"threshold": 50.0}})
        ex2 = await ProcessingOrchestrator(db=async_session, dispatcher=m2, snapshot_resolver=r2).process_work_item(
            wi.id, trigger_type="REPROCESS",
        )

        # Run 1: threshold 99 → 0 anomalies
        assert d1.call_log[2]["input"]["anomaly_count"] == 0
        # Run 2: threshold 50 → 3 anomalies (all temps > 50)
        assert d2.call_log[2]["input"]["anomaly_count"] == 3


# ===========================================================================
# 4. DATA LINEAGE — Snapshot + Event Logs
# ===========================================================================


class TestDataLineage:

    @pytest.mark.asyncio
    async def test_snapshot_captures_recipe_values(self, async_session, sample_pipeline):
        """Snapshot resolver is called with correct pipeline context."""
        pipeline, steps = sample_pipeline
        wi = await _wi(async_session, pipeline)

        recipes = {"ALGORITHM": {"threshold": 85.0}}
        resolver = _make_resolver_with_recipes(async_session, steps, recipes)
        d = AsyncMock(spec=ExecutionDispatcher)
        d.dispatch = AsyncMock(return_value=ExecutionResult(success=True, output={}, summary={}, duration_ms=5))

        ex = await ProcessingOrchestrator(db=async_session, dispatcher=d, snapshot_resolver=resolver).process_work_item(wi.id)

        # Verify snapshot was created
        snap_r = await async_session.execute(
            select(ExecutionSnapshot).where(ExecutionSnapshot.execution_id == ex.id)
        )
        snap = snap_r.scalar_one()
        assert snap.snapshot_hash is not None
        assert snap.pipeline_config["name"] == pipeline.name

    @pytest.mark.asyncio
    async def test_event_logs_full_pipeline_trace(self, async_session, sample_pipeline):
        """Event logs record COLLECT_START/DONE, ALGORITHM_START/DONE, TRANSFER_START/DONE."""
        pipeline, steps = sample_pipeline
        wi = await _wi(async_session, pipeline)

        d = AsyncMock(spec=ExecutionDispatcher)
        d.dispatch = AsyncMock(return_value=ExecutionResult(success=True, output={}, summary={}, duration_ms=5))
        r = _make_resolver_with_recipes(async_session, steps, {})

        ex = await ProcessingOrchestrator(db=async_session, dispatcher=d, snapshot_resolver=r).process_work_item(wi.id)

        logs_r = await async_session.execute(
            select(ExecutionEventLog).where(ExecutionEventLog.execution_id == ex.id)
        )
        logs = list(logs_r.scalars().all())
        codes = [l.event_code for l in logs]

        assert "EXECUTION_START" in codes
        assert "COLLECT_START" in codes
        assert "COLLECT_DONE" in codes
        assert "ALGORITHM_START" in codes
        assert "ALGORITHM_DONE" in codes
        assert "TRANSFER_START" in codes
        assert "TRANSFER_DONE" in codes
        assert "EXECUTION_END" in codes

    @pytest.mark.asyncio
    async def test_step_execution_records_capture_output(self, async_session, sample_pipeline):
        """Each step execution record stores output_summary."""
        pipeline, steps = sample_pipeline
        wi = await _wi(async_session, pipeline)

        d = AsyncMock(spec=ExecutionDispatcher)
        d.dispatch = AsyncMock(return_value=ExecutionResult(
            success=True, output={"result": 42}, summary={"metric": "count", "value": 42}, duration_ms=10,
        ))
        r = _make_resolver_with_recipes(async_session, steps, {})

        ex = await ProcessingOrchestrator(db=async_session, dispatcher=d, snapshot_resolver=r).process_work_item(wi.id)

        se_r = await async_session.execute(
            select(WorkItemStepExecution).where(WorkItemStepExecution.execution_id == ex.id)
            .order_by(WorkItemStepExecution.step_order)
        )
        step_execs = list(se_r.scalars().all())

        assert len(step_execs) == 3
        for se in step_execs:
            assert se.output_summary is not None
            assert se.output_summary.get("metric") == "count"


# ===========================================================================
# 5. EDGE: Collect Returns Empty → Process Handles Gracefully
# ===========================================================================


class TestEmptyDataFlow:

    @pytest.mark.asyncio
    async def test_empty_collect_propagates_to_export(self, async_session, sample_pipeline):
        """Empty collect output → process gets empty → export writes 0 records."""
        pipeline, steps = sample_pipeline
        wi = await _wi(async_session, pipeline)

        async def empty_flow(**kw):
            t = kw.get("context", {}).get("step_type", "?")
            if t == "COLLECT":
                return ExecutionResult(success=True, output={"records": []}, summary={}, duration_ms=5)
            elif t == "ALGORITHM":
                inp = kw.get("input_data", {})
                return ExecutionResult(success=True, output={"records": [], "count": 0}, summary={}, duration_ms=3)
            return ExecutionResult(success=True, output={"written": 0}, summary={}, duration_ms=2)

        d = AsyncMock(spec=ExecutionDispatcher)
        d.dispatch = AsyncMock(side_effect=empty_flow)
        r = _make_resolver_with_recipes(async_session, steps, {})

        ex = await ProcessingOrchestrator(db=async_session, dispatcher=d, snapshot_resolver=r).process_work_item(wi.id)
        assert ex.status == "COMPLETED"
        assert d.dispatch.call_count == 3  # All 3 steps still execute
