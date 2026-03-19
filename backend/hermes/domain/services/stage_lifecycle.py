"""Stage runtime lifecycle management service."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func as sa_func
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hermes.domain.models.execution import WorkItem, WorkItemExecution, WorkItemStepExecution
from hermes.domain.models.monitoring import StageRuntimeState
from hermes.domain.models.pipeline import PipelineStep

logger = logging.getLogger(__name__)


@dataclass
class StageQueueSummary:
    """Queue depth and throughput counters for a single pipeline stage."""

    stage_id: uuid.UUID
    stage_order: int
    stage_type: str
    runtime_status: str  # RUNNING, STOPPED, DRAINING, BLOCKED, ERROR
    queued_count: int = 0     # work items waiting before this stage
    in_flight_count: int = 0  # work items currently being processed by this stage
    completed_count: int = 0  # work items that have passed through this stage


class StageLifecycleManager:
    """Manages per-stage runtime states within a pipeline activation."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # State mutations
    # ------------------------------------------------------------------

    async def stop_stage(
        self,
        activation_id: uuid.UUID,
        step_id: uuid.UUID,
        stopped_by: str = "operator",
    ) -> StageRuntimeState:
        """Stop a stage: set runtime_status=STOPPED and record the timestamp.

        Creates a new ``StageRuntimeState`` row if one does not yet exist for
        this (activation, step) pair.
        """
        state = await self.get_stage_runtime(activation_id, step_id)
        now = datetime.now(UTC)

        if state is None:
            state = StageRuntimeState(
                pipeline_activation_id=activation_id,
                pipeline_step_id=step_id,
                runtime_status="STOPPED",
                stopped_at=now,
                stopped_by=stopped_by,
            )
            self.db.add(state)
        else:
            state.runtime_status = "STOPPED"
            state.stopped_at = now
            state.stopped_by = stopped_by

        await self.db.flush()
        logger.info(
            "Stopped stage %s on activation %s (by %s)", step_id, activation_id, stopped_by
        )
        return state

    async def resume_stage(
        self,
        activation_id: uuid.UUID,
        step_id: uuid.UUID,
    ) -> StageRuntimeState:
        """Resume a stopped stage: set runtime_status=RUNNING and record the timestamp.

        Creates a new ``StageRuntimeState`` row if one does not yet exist.
        """
        state = await self.get_stage_runtime(activation_id, step_id)
        now = datetime.now(UTC)

        if state is None:
            state = StageRuntimeState(
                pipeline_activation_id=activation_id,
                pipeline_step_id=step_id,
                runtime_status="RUNNING",
                resumed_at=now,
            )
            self.db.add(state)
        else:
            state.runtime_status = "RUNNING"
            state.resumed_at = now

        await self.db.flush()
        logger.info("Resumed stage %s on activation %s", step_id, activation_id)
        return state

    async def initialize_stage_states(
        self,
        activation_id: uuid.UUID,
        step_ids: list[uuid.UUID],
    ) -> list[StageRuntimeState]:
        """Create RUNNING ``StageRuntimeState`` rows for each step on activation start.

        Any step that already has a state row is skipped so that this method is
        safe to call more than once.
        """
        # Find steps that already have a state so we don't double-insert.
        existing_stmt = select(StageRuntimeState.pipeline_step_id).where(
            StageRuntimeState.pipeline_activation_id == activation_id,
            StageRuntimeState.pipeline_step_id.in_(step_ids),
        )
        existing_result = await self.db.execute(existing_stmt)
        already_present: set[uuid.UUID] = set(existing_result.scalars().all())

        new_states: list[StageRuntimeState] = []
        for step_id in step_ids:
            if step_id in already_present:
                continue
            state = StageRuntimeState(
                pipeline_activation_id=activation_id,
                pipeline_step_id=step_id,
                runtime_status="RUNNING",
            )
            self.db.add(state)
            new_states.append(state)

        if new_states:
            await self.db.flush()
            logger.info(
                "Initialized %d stage states for activation %s",
                len(new_states),
                activation_id,
            )

        return new_states

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    async def get_stage_runtime(
        self,
        activation_id: uuid.UUID,
        step_id: uuid.UUID,
    ) -> StageRuntimeState | None:
        """Fetch the current ``StageRuntimeState`` for a (activation, step) pair."""
        stmt = select(StageRuntimeState).where(
            StageRuntimeState.pipeline_activation_id == activation_id,
            StageRuntimeState.pipeline_step_id == step_id,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_queue_summary(
        self, activation_id: uuid.UUID
    ) -> list[StageQueueSummary]:
        """Compute queue depth and throughput counters for every stage in an activation.

        Definitions
        -----------
        queued_count
            Work items whose last *successfully completed* step execution is the
            stage immediately before the current stage (i.e. they are waiting to
            enter it).  For stage 1 this is work items that have no completed
            step executions at all yet.
        in_flight_count
            Work items that have a step execution for this stage in a non-terminal
            state (PENDING or RUNNING).
        completed_count
            Work items that have a step execution for this stage in a terminal
            success state (DONE / COMPLETED / SUCCESS).
        """
        # 1. Load all pipeline steps for this activation in order.
        steps_stmt = (
            select(PipelineStep)
            .join(
                StageRuntimeState,
                (StageRuntimeState.pipeline_step_id == PipelineStep.id)
                & (StageRuntimeState.pipeline_activation_id == activation_id),
            )
            .order_by(PipelineStep.step_order)
        )
        steps_result = await self.db.execute(steps_stmt)
        steps: list[PipelineStep] = list(steps_result.scalars().all())

        if not steps:
            # Fall back: load steps via work items belonging to this activation.
            steps_fallback_stmt = (
                select(PipelineStep)
                .join(
                    WorkItemStepExecution,
                    WorkItemStepExecution.pipeline_step_id == PipelineStep.id,
                )
                .join(
                    WorkItemExecution,
                    WorkItemExecution.id == WorkItemStepExecution.execution_id,
                )
                .join(
                    WorkItem,
                    (WorkItem.id == WorkItemExecution.work_item_id)
                    & (WorkItem.pipeline_activation_id == activation_id),
                )
                .distinct()
                .order_by(PipelineStep.step_order)
            )
            fb_result = await self.db.execute(steps_fallback_stmt)
            steps = list(fb_result.scalars().all())

        if not steps:
            return []

        # 2. Load runtime states keyed by step id.
        states_stmt = select(StageRuntimeState).where(
            StageRuntimeState.pipeline_activation_id == activation_id
        )
        states_result = await self.db.execute(states_stmt)
        states_by_step: dict[uuid.UUID, StageRuntimeState] = {
            s.pipeline_step_id: s for s in states_result.scalars().all()
        }

        # 3. Determine the last completed step_order for each work item.
        #    "completed" = step execution with status in (DONE, COMPLETED, SUCCESS).
        #    WorkItemStepExecution → WorkItemExecution (execution_id) → WorkItem (work_item_id)
        _COMPLETE_STATUSES = ("DONE", "COMPLETED", "SUCCESS")

        last_done_stmt = (
            select(
                WorkItemExecution.work_item_id,
                sa_func.max(WorkItemStepExecution.step_order).label("max_order"),
            )
            .join(WorkItemExecution, WorkItemExecution.id == WorkItemStepExecution.execution_id)
            .join(WorkItem, WorkItem.id == WorkItemExecution.work_item_id)
            .where(
                WorkItem.pipeline_activation_id == activation_id,
                WorkItemStepExecution.status.in_(_COMPLETE_STATUSES),
            )
            .group_by(WorkItemExecution.work_item_id)
        )
        last_done_result = await self.db.execute(last_done_stmt)
        last_done_by_wi: dict[uuid.UUID, int] = {
            row.work_item_id: row.max_order for row in last_done_result
        }

        # In-flight: (work_item_id, step_id) pairs where status is PENDING/RUNNING.
        _INFLIGHT_STATUSES = ("PENDING", "RUNNING")
        inflight_stmt = (
            select(
                WorkItemExecution.work_item_id,
                WorkItemStepExecution.pipeline_step_id,
            )
            .join(WorkItemExecution, WorkItemExecution.id == WorkItemStepExecution.execution_id)
            .join(WorkItem, WorkItem.id == WorkItemExecution.work_item_id)
            .where(
                WorkItem.pipeline_activation_id == activation_id,
                WorkItemStepExecution.status.in_(_INFLIGHT_STATUSES),
            )
        )
        inflight_result = await self.db.execute(inflight_stmt)
        inflight_pairs: set[tuple[uuid.UUID, uuid.UUID]] = {
            (row.work_item_id, row.pipeline_step_id) for row in inflight_result
        }

        # Completed: count per step_id where status is terminal success.
        completed_count_stmt = (
            select(
                WorkItemStepExecution.pipeline_step_id,
                sa_func.count(WorkItemStepExecution.id).label("cnt"),
            )
            .join(WorkItemExecution, WorkItemExecution.id == WorkItemStepExecution.execution_id)
            .join(WorkItem, WorkItem.id == WorkItemExecution.work_item_id)
            .where(
                WorkItem.pipeline_activation_id == activation_id,
                WorkItemStepExecution.status.in_(_COMPLETE_STATUSES),
            )
            .group_by(WorkItemStepExecution.pipeline_step_id)
        )
        completed_count_result = await self.db.execute(completed_count_stmt)
        completed_by_step: dict[uuid.UUID, int] = {
            row.pipeline_step_id: row.cnt for row in completed_count_result
        }

        # Total work items for this activation (needed for stage-1 queued count).
        total_wi_stmt = select(sa_func.count(WorkItem.id)).where(
            WorkItem.pipeline_activation_id == activation_id
        )
        total_wi_result = await self.db.execute(total_wi_stmt)
        total_wi: int = total_wi_result.scalar() or 0

        # 4. Build summaries.
        step_order_by_id = {s.id: s.step_order for s in steps}
        summaries: list[StageQueueSummary] = []

        for step in steps:
            state = states_by_step.get(step.id)
            runtime_status = state.runtime_status if state else "RUNNING"

            # queued_count: work items whose last completed step = (step_order - 1),
            # or no completed steps at all for stage 1.
            preceding_order = step.step_order - 1
            if preceding_order == 0:
                # Stage 1 — queued means no completed step executions yet
                queued_count = total_wi - sum(
                    1 for max_ord in last_done_by_wi.values() if max_ord >= 1
                ) - sum(
                    1
                    for (_, sid) in inflight_pairs
                    if step_order_by_id.get(sid) == step.step_order
                )
                queued_count = max(queued_count, 0)
            else:
                queued_count = sum(
                    1
                    for wi_id, max_ord in last_done_by_wi.items()
                    if max_ord == preceding_order
                    and (wi_id, step.id) not in inflight_pairs
                )

            # in_flight_count: work items with a PENDING/RUNNING execution for this step.
            in_flight_count = sum(
                1 for (_, sid) in inflight_pairs if sid == step.id
            )

            # completed_count: terminal-success executions for this step.
            completed_count = completed_by_step.get(step.id, 0)

            summaries.append(
                StageQueueSummary(
                    stage_id=step.id,
                    stage_order=step.step_order,
                    stage_type=step.step_type,
                    runtime_status=runtime_status,
                    queued_count=queued_count,
                    in_flight_count=in_flight_count,
                    completed_count=completed_count,
                )
            )

        return summaries
