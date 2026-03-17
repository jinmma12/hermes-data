"""Pipeline Stage Composition E2E Tests.

Verifies that pipeline stage connections (edges in the visual designer) correctly
persist to the database with proper ordering, and that reorder / delete / add
/ duplicate / lifecycle operations maintain data integrity.

These tests use the PipelineManager service layer directly against an in-memory
SQLite database, ensuring the full stack from service → ORM → DB is validated.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from vessel.domain.models.monitoring import PipelineActivation
from vessel.domain.models.pipeline import PipelineInstance, PipelineStep
from vessel.domain.services.pipeline_manager import PipelineManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def make_pipeline(
    db: AsyncSession,
    name: str = "comp-test",
    status: str = "DRAFT",
    monitoring_type: str = "FILE_MONITOR",
) -> PipelineInstance:
    pipeline = PipelineInstance(
        name=name,
        description=f"Test pipeline: {name}",
        monitoring_type=monitoring_type,
        monitoring_config={"path": "/data"},
        status=status,
    )
    db.add(pipeline)
    await db.flush()
    return pipeline


async def add_step(
    db: AsyncSession,
    pipeline_id: uuid.UUID,
    order: int,
    step_type: str,
    ref_type: str | None = None,
    ref_id: uuid.UUID | None = None,
    on_error: str = "STOP",
    is_enabled: bool = True,
) -> PipelineStep:
    if ref_type is None:
        ref_type = {"COLLECT": "COLLECTOR", "ALGORITHM": "ALGORITHM", "TRANSFER": "TRANSFER"}[step_type]
    step = PipelineStep(
        pipeline_instance_id=pipeline_id,
        step_order=order,
        step_type=step_type,
        ref_type=ref_type,
        ref_id=ref_id or uuid.uuid4(),
        on_error=on_error,
        is_enabled=is_enabled,
    )
    db.add(step)
    await db.flush()
    return step


async def get_steps(db: AsyncSession, pipeline_id: uuid.UUID) -> list[PipelineStep]:
    result = await db.execute(
        select(PipelineStep)
        .where(PipelineStep.pipeline_instance_id == pipeline_id)
        .order_by(PipelineStep.step_order)
    )
    return list(result.scalars().all())


# ===========================================================================
# 1. Basic Stage Composition — DB Persistence
# ===========================================================================


class TestStageCompositionPersistence:
    """Verify that pipeline stages (edges) persist to DB correctly."""

    @pytest.mark.asyncio
    async def test_three_stages_persist_in_order(self, async_session: AsyncSession):
        p = await make_pipeline(async_session)
        await add_step(async_session, p.id, 1, "COLLECT")
        await add_step(async_session, p.id, 2, "ALGORITHM")
        await add_step(async_session, p.id, 3, "TRANSFER")

        steps = await get_steps(async_session, p.id)
        assert len(steps) == 3
        assert [s.step_type for s in steps] == ["COLLECT", "ALGORITHM", "TRANSFER"]
        assert [s.step_order for s in steps] == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_steps_have_correct_ref_types(self, async_session: AsyncSession):
        p = await make_pipeline(async_session)
        await add_step(async_session, p.id, 1, "COLLECT")
        await add_step(async_session, p.id, 2, "ALGORITHM")
        await add_step(async_session, p.id, 3, "TRANSFER")

        steps = await get_steps(async_session, p.id)
        assert [s.ref_type for s in steps] == ["COLLECTOR", "ALGORITHM", "TRANSFER"]

    @pytest.mark.asyncio
    async def test_steps_belong_to_correct_pipeline(self, async_session: AsyncSession):
        p1 = await make_pipeline(async_session, "pipeline-A")
        p2 = await make_pipeline(async_session, "pipeline-B")
        await add_step(async_session, p1.id, 1, "COLLECT")
        await add_step(async_session, p2.id, 1, "COLLECT")
        await add_step(async_session, p2.id, 2, "TRANSFER")

        assert len(await get_steps(async_session, p1.id)) == 1
        assert len(await get_steps(async_session, p2.id)) == 2

    @pytest.mark.asyncio
    async def test_empty_pipeline_has_zero_steps(self, async_session: AsyncSession):
        p = await make_pipeline(async_session)
        assert len(await get_steps(async_session, p.id)) == 0

    @pytest.mark.asyncio
    async def test_five_stages_order_preserved(self, async_session: AsyncSession):
        p = await make_pipeline(async_session)
        for i, t in enumerate(["COLLECT", "ALGORITHM", "ALGORITHM", "ALGORITHM", "TRANSFER"], 1):
            await add_step(async_session, p.id, i, t)

        steps = await get_steps(async_session, p.id)
        assert len(steps) == 5
        assert [s.step_order for s in steps] == [1, 2, 3, 4, 5]

    @pytest.mark.asyncio
    async def test_ref_ids_point_to_specific_instances(self, async_session: AsyncSession):
        ref_ids = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]
        p = await make_pipeline(async_session)
        await add_step(async_session, p.id, 1, "COLLECT", ref_id=ref_ids[0])
        await add_step(async_session, p.id, 2, "ALGORITHM", ref_id=ref_ids[1])
        await add_step(async_session, p.id, 3, "TRANSFER", ref_id=ref_ids[2])

        steps = await get_steps(async_session, p.id)
        assert [s.ref_id for s in steps] == ref_ids


# ===========================================================================
# 2. Step Reordering via PipelineManager
# ===========================================================================


class TestStepReordering:
    """Verify that reordering steps updates step_order correctly."""

    @pytest.mark.asyncio
    async def test_reorder_swap_first_and_last(self, async_session: AsyncSession):
        p = await make_pipeline(async_session)
        s1 = await add_step(async_session, p.id, 1, "COLLECT")
        s2 = await add_step(async_session, p.id, 2, "ALGORITHM")
        s3 = await add_step(async_session, p.id, 3, "TRANSFER")

        mgr = PipelineManager(async_session)
        reordered = await mgr.reorder_steps(p.id, [s3.id, s2.id, s1.id])

        assert [s.step_order for s in reordered] == [1, 2, 3]
        assert [s.id for s in reordered] == [s3.id, s2.id, s1.id]

    @pytest.mark.asyncio
    async def test_reorder_move_middle_to_end(self, async_session: AsyncSession):
        p = await make_pipeline(async_session)
        s1 = await add_step(async_session, p.id, 1, "COLLECT")
        s2 = await add_step(async_session, p.id, 2, "ALGORITHM")
        s3 = await add_step(async_session, p.id, 3, "TRANSFER")

        mgr = PipelineManager(async_session)
        reordered = await mgr.reorder_steps(p.id, [s1.id, s3.id, s2.id])

        assert [s.id for s in reordered] == [s1.id, s3.id, s2.id]
        assert [s.step_order for s in reordered] == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_reorder_does_not_affect_other_pipeline(self, async_session: AsyncSession):
        pA = await make_pipeline(async_session, "A")
        pB = await make_pipeline(async_session, "B")
        sA1 = await add_step(async_session, pA.id, 1, "COLLECT")
        sA2 = await add_step(async_session, pA.id, 2, "TRANSFER")
        sB1 = await add_step(async_session, pB.id, 1, "COLLECT")

        mgr = PipelineManager(async_session)
        await mgr.reorder_steps(pA.id, [sA2.id, sA1.id])

        bSteps = await get_steps(async_session, pB.id)
        assert len(bSteps) == 1
        assert bSteps[0].step_order == 1

    @pytest.mark.asyncio
    async def test_reorder_wrong_ids_raises(self, async_session: AsyncSession):
        p = await make_pipeline(async_session)
        s1 = await add_step(async_session, p.id, 1, "COLLECT")

        mgr = PipelineManager(async_session)
        with pytest.raises(ValueError, match="step_ids must contain exactly"):
            await mgr.reorder_steps(p.id, [uuid.uuid4()])


# ===========================================================================
# 3. Step Deletion
# ===========================================================================


class TestStepDeletion:
    """Verify that deleting steps maintains DB integrity."""

    @pytest.mark.asyncio
    async def test_delete_middle_step(self, async_session: AsyncSession):
        p = await make_pipeline(async_session)
        s1 = await add_step(async_session, p.id, 1, "COLLECT")
        s2 = await add_step(async_session, p.id, 2, "ALGORITHM")
        s3 = await add_step(async_session, p.id, 3, "TRANSFER")

        mgr = PipelineManager(async_session)
        await mgr.remove_step(p.id, s2.id)

        steps = await get_steps(async_session, p.id)
        assert len(steps) == 2
        assert [s.id for s in steps] == [s1.id, s3.id]

    @pytest.mark.asyncio
    async def test_delete_all_steps_pipeline_survives(self, async_session: AsyncSession):
        p = await make_pipeline(async_session)
        s1 = await add_step(async_session, p.id, 1, "COLLECT")
        s2 = await add_step(async_session, p.id, 2, "TRANSFER")

        mgr = PipelineManager(async_session)
        await mgr.remove_step(p.id, s1.id)
        await mgr.remove_step(p.id, s2.id)

        steps = await get_steps(async_session, p.id)
        assert len(steps) == 0

        # Pipeline still exists
        loaded = await async_session.get(PipelineInstance, p.id)
        assert loaded is not None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_step_raises(self, async_session: AsyncSession):
        p = await make_pipeline(async_session)
        mgr = PipelineManager(async_session)
        with pytest.raises(ValueError, match="not found"):
            await mgr.remove_step(p.id, uuid.uuid4())

    @pytest.mark.asyncio
    async def test_delete_step_from_wrong_pipeline_raises(self, async_session: AsyncSession):
        pA = await make_pipeline(async_session, "A")
        pB = await make_pipeline(async_session, "B")
        sA = await add_step(async_session, pA.id, 1, "COLLECT")

        mgr = PipelineManager(async_session)
        with pytest.raises(ValueError, match="not found"):
            await mgr.remove_step(pB.id, sA.id)


# ===========================================================================
# 4. Add Step via PipelineManager (auto-order)
# ===========================================================================


class TestAddStepViaManager:
    """Verify PipelineManager.add_step auto-ordering."""

    @pytest.mark.asyncio
    async def test_add_step_auto_order_appends(self, async_session: AsyncSession):
        p = await make_pipeline(async_session)
        mgr = PipelineManager(async_session)
        s1 = await mgr.add_step(p.id, "COLLECT", "COLLECTOR", uuid.uuid4())
        s2 = await mgr.add_step(p.id, "ALGORITHM", "ALGORITHM", uuid.uuid4())
        s3 = await mgr.add_step(p.id, "TRANSFER", "TRANSFER", uuid.uuid4())

        assert s1.step_order == 1
        assert s2.step_order == 2
        assert s3.step_order == 3

    @pytest.mark.asyncio
    async def test_add_step_explicit_order(self, async_session: AsyncSession):
        p = await make_pipeline(async_session)
        mgr = PipelineManager(async_session)
        s = await mgr.add_step(p.id, "COLLECT", "COLLECTOR", uuid.uuid4(), step_order=5)
        assert s.step_order == 5

    @pytest.mark.asyncio
    async def test_add_step_after_deletion_continues_sequence(self, async_session: AsyncSession):
        p = await make_pipeline(async_session)
        mgr = PipelineManager(async_session)
        s1 = await mgr.add_step(p.id, "COLLECT", "COLLECTOR", uuid.uuid4())
        s2 = await mgr.add_step(p.id, "ALGORITHM", "ALGORITHM", uuid.uuid4())

        await mgr.remove_step(p.id, s2.id)
        # Next auto-order should still be 2 (last remaining is s1 with order=1)
        s3 = await mgr.add_step(p.id, "TRANSFER", "TRANSFER", uuid.uuid4())
        assert s3.step_order == 2


# ===========================================================================
# 5. Full Pipeline Lifecycle with Stages
# ===========================================================================


class TestFullPipelineLifecycle:
    """Verify the complete create → add stages → activate → status flow."""

    @pytest.mark.asyncio
    async def test_create_add_stages_activate(
        self,
        async_session: AsyncSession,
        sample_collector_instance,
        sample_algorithm_instance,
        sample_transfer_instance,
    ):
        coll, _ = sample_collector_instance
        algo, _ = sample_algorithm_instance
        xfer, _ = sample_transfer_instance

        mgr = PipelineManager(async_session)

        # 1. Create pipeline
        pipeline = await mgr.create_pipeline(
            name="lifecycle-test",
            monitoring_type="FILE_MONITOR",
            monitoring_config={"path": "/data"},
        )
        assert pipeline.status == "DRAFT"

        # 2. Add stages (simulating designer edges)
        s1 = await mgr.add_step(pipeline.id, "COLLECT", "COLLECTOR", coll.id)
        s2 = await mgr.add_step(pipeline.id, "ALGORITHM", "ALGORITHM", algo.id)
        s3 = await mgr.add_step(pipeline.id, "TRANSFER", "TRANSFER", xfer.id)

        assert [s.step_order for s in [s1, s2, s3]] == [1, 2, 3]

        # 3. Activate
        activation = await mgr.activate_pipeline(pipeline.id)
        assert activation.status == "STARTING"

        # 4. Verify pipeline is ACTIVE
        loaded = await mgr.get_pipeline(pipeline.id)
        assert loaded is not None
        assert loaded.status == "ACTIVE"
        assert len(loaded.steps) == 3

    @pytest.mark.asyncio
    async def test_activate_deactivate_reactivate(
        self,
        async_session: AsyncSession,
        sample_collector_instance,
    ):
        coll, _ = sample_collector_instance
        mgr = PipelineManager(async_session)

        pipeline = await mgr.create_pipeline("toggle-test", "FILE_MONITOR")
        await mgr.add_step(pipeline.id, "COLLECT", "COLLECTOR", coll.id)

        # Activate
        act1 = await mgr.activate_pipeline(pipeline.id)
        assert act1.status == "STARTING"

        # Mark as running (worker would do this)
        act1.status = "RUNNING"
        await async_session.flush()

        # Deactivate
        await mgr.deactivate_pipeline(pipeline.id)
        p = await mgr.get_pipeline(pipeline.id)
        assert p is not None
        assert p.status == "PAUSED"

        # Reactivate
        act2 = await mgr.activate_pipeline(pipeline.id)
        p = await mgr.get_pipeline(pipeline.id)
        assert p is not None
        assert p.status == "ACTIVE"

        # Two activations total
        result = await async_session.execute(
            select(func.count())
            .select_from(PipelineActivation)
            .where(PipelineActivation.pipeline_instance_id == pipeline.id)
        )
        assert result.scalar() == 2

    @pytest.mark.asyncio
    async def test_activate_empty_pipeline_fails(self, async_session: AsyncSession):
        mgr = PipelineManager(async_session)
        pipeline = await mgr.create_pipeline("empty-test", "FILE_MONITOR")

        with pytest.raises(ValueError, match="validation failed"):
            await mgr.activate_pipeline(pipeline.id)

    @pytest.mark.asyncio
    async def test_modify_stages_while_paused(
        self,
        async_session: AsyncSession,
        sample_collector_instance,
        sample_algorithm_instance,
        sample_transfer_instance,
    ):
        coll, _ = sample_collector_instance
        algo, _ = sample_algorithm_instance
        xfer, _ = sample_transfer_instance
        mgr = PipelineManager(async_session)

        pipeline = await mgr.create_pipeline("modify-test", "FILE_MONITOR")
        s1 = await mgr.add_step(pipeline.id, "COLLECT", "COLLECTOR", coll.id)
        s2 = await mgr.add_step(pipeline.id, "TRANSFER", "TRANSFER", xfer.id)

        # Activate + deactivate
        act = await mgr.activate_pipeline(pipeline.id)
        act.status = "RUNNING"
        await async_session.flush()
        await mgr.deactivate_pipeline(pipeline.id)

        # Add a processor in the middle while paused
        await mgr.reorder_steps(pipeline.id, [s1.id, s2.id])  # normalize
        s_new = await mgr.add_step(pipeline.id, "ALGORITHM", "ALGORITHM", algo.id, step_order=2)
        s2.step_order = 3
        await async_session.flush()

        steps = await get_steps(async_session, pipeline.id)
        assert len(steps) == 3
        assert [s.step_type for s in steps] == ["COLLECT", "ALGORITHM", "TRANSFER"]

    @pytest.mark.asyncio
    async def test_get_pipeline_status(
        self,
        async_session: AsyncSession,
        sample_collector_instance,
    ):
        coll, _ = sample_collector_instance
        mgr = PipelineManager(async_session)

        pipeline = await mgr.create_pipeline("status-test", "FILE_MONITOR")
        await mgr.add_step(pipeline.id, "COLLECT", "COLLECTOR", coll.id)

        activation = await mgr.activate_pipeline(pipeline.id)
        activation.status = "RUNNING"
        await async_session.flush()

        status = await mgr.get_pipeline_status(pipeline.id)
        assert status.status == "ACTIVE"
        assert status.step_count == 1
        assert status.active_activation_id == activation.id
        assert status.activation_status == "RUNNING"


# ===========================================================================
# 6. Duplicate Pipeline
# ===========================================================================


class TestDuplicatePipeline:
    """Verify pipeline duplication copies steps correctly."""

    @pytest.mark.asyncio
    async def test_duplicate_copies_steps_with_refs(self, async_session: AsyncSession):
        ref_ids = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]
        p = await make_pipeline(async_session, "original")
        await add_step(async_session, p.id, 1, "COLLECT", ref_id=ref_ids[0])
        await add_step(async_session, p.id, 2, "ALGORITHM", ref_id=ref_ids[1])
        await add_step(async_session, p.id, 3, "TRANSFER", ref_id=ref_ids[2])

        # Duplicate
        copy = await make_pipeline(async_session, "original (Copy)", status="DRAFT")
        orig_steps = await get_steps(async_session, p.id)
        for step in orig_steps:
            await add_step(
                async_session,
                copy.id,
                step.step_order,
                step.step_type,
                ref_type=step.ref_type,
                ref_id=step.ref_id,
            )

        copy_steps = await get_steps(async_session, copy.id)
        assert len(copy_steps) == 3
        assert copy.status == "DRAFT"
        assert copy.name == "original (Copy)"
        assert [s.ref_id for s in copy_steps] == ref_ids

    @pytest.mark.asyncio
    async def test_duplicate_is_independent(self, async_session: AsyncSession):
        p = await make_pipeline(async_session, "orig")
        s1 = await add_step(async_session, p.id, 1, "COLLECT")
        await add_step(async_session, p.id, 2, "TRANSFER")

        copy = await make_pipeline(async_session, "orig (Copy)")
        orig_steps = await get_steps(async_session, p.id)
        for step in orig_steps:
            await add_step(async_session, copy.id, step.step_order, step.step_type)

        # Delete step from original — copy unaffected
        mgr = PipelineManager(async_session)
        await mgr.remove_step(p.id, s1.id)

        assert len(await get_steps(async_session, p.id)) == 1
        assert len(await get_steps(async_session, copy.id)) == 2


# ===========================================================================
# 7. Step Enable/Disable
# ===========================================================================


class TestStepEnableDisable:

    @pytest.mark.asyncio
    async def test_disable_step_persists(self, async_session: AsyncSession):
        p = await make_pipeline(async_session)
        s = await add_step(async_session, p.id, 1, "COLLECT")

        s.is_enabled = False
        await async_session.flush()

        loaded = await async_session.get(PipelineStep, s.id)
        assert loaded is not None
        assert loaded.is_enabled is False

    @pytest.mark.asyncio
    async def test_count_enabled_steps(self, async_session: AsyncSession):
        p = await make_pipeline(async_session)
        s1 = await add_step(async_session, p.id, 1, "COLLECT")
        s2 = await add_step(async_session, p.id, 2, "ALGORITHM")
        s3 = await add_step(async_session, p.id, 3, "TRANSFER")

        s2.is_enabled = False
        await async_session.flush()

        result = await async_session.execute(
            select(func.count())
            .select_from(PipelineStep)
            .where(
                PipelineStep.pipeline_instance_id == p.id,
                PipelineStep.is_enabled == True,
            )
        )
        assert result.scalar() == 2
