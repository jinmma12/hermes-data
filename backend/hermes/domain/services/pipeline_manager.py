"""Pipeline lifecycle management service."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from hermes.domain.models.instance import (
    AlgorithmInstance,
    CollectorInstance,
    TransferInstance,
)
from hermes.domain.models.monitoring import PipelineActivation
from hermes.domain.models.pipeline import PipelineInstance, PipelineStep

logger = logging.getLogger(__name__)


@dataclass
class ValidationIssue:
    """A single validation issue found in a pipeline."""

    step_id: uuid.UUID | None
    step_order: int | None
    severity: str  # ERROR | WARNING
    message: str


@dataclass
class ValidationResult:
    """Result of validating a pipeline configuration."""

    valid: bool
    issues: list[ValidationIssue] = field(default_factory=list)


@dataclass
class PipelineStatus:
    """Current status snapshot of a pipeline."""

    pipeline_id: uuid.UUID
    pipeline_name: str
    status: str
    step_count: int
    active_activation_id: uuid.UUID | None = None
    activation_status: str | None = None
    last_heartbeat_at: datetime | None = None
    work_item_count: int = 0


# Mapping from ref_type to the SQLAlchemy model for instance lookup.
_INSTANCE_MODELS: dict[str, type] = {
    "COLLECTOR": CollectorInstance,
    "ALGORITHM": AlgorithmInstance,
    "TRANSFER": TransferInstance,
}


class PipelineManager:
    """Manages the full lifecycle of pipeline instances and their steps."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Pipeline CRUD
    # ------------------------------------------------------------------

    async def create_pipeline(
        self,
        name: str,
        monitoring_type: str,
        monitoring_config: dict[str, Any] | None = None,
        description: str | None = None,
    ) -> PipelineInstance:
        """Create a new pipeline in DRAFT status."""
        pipeline = PipelineInstance(
            name=name,
            description=description,
            monitoring_type=monitoring_type,
            monitoring_config=monitoring_config or {},
            status="DRAFT",
        )
        self.db.add(pipeline)
        await self.db.flush()
        logger.info("Created pipeline %s (%s)", pipeline.id, name)
        return pipeline

    async def get_pipeline(self, pipeline_id: uuid.UUID) -> PipelineInstance | None:
        """Fetch a pipeline with its steps eagerly loaded."""
        stmt = (
            select(PipelineInstance)
            .options(selectinload(PipelineInstance.steps))
            .where(PipelineInstance.id == pipeline_id)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # Step management
    # ------------------------------------------------------------------

    async def add_step(
        self,
        pipeline_id: uuid.UUID,
        step_type: str,
        ref_type: str,
        ref_id: uuid.UUID,
        step_order: int | None = None,
    ) -> PipelineStep:
        """Add a processing step to a pipeline.

        If *step_order* is ``None`` the step is appended after the last
        existing step.
        """
        if step_order is None:
            stmt = (
                select(PipelineStep)
                .where(PipelineStep.pipeline_instance_id == pipeline_id)
                .order_by(PipelineStep.step_order.desc())
                .limit(1)
            )
            result = await self.db.execute(stmt)
            last = result.scalar_one_or_none()
            step_order = (last.step_order + 1) if last else 1

        step = PipelineStep(
            pipeline_instance_id=pipeline_id,
            step_order=step_order,
            step_type=step_type,
            ref_type=ref_type,
            ref_id=ref_id,
        )
        self.db.add(step)
        await self.db.flush()
        logger.info("Added step %s (order=%d) to pipeline %s", step.id, step_order, pipeline_id)
        return step

    async def reorder_steps(
        self, pipeline_id: uuid.UUID, step_ids: list[uuid.UUID]
    ) -> list[PipelineStep]:
        """Re-order steps within a pipeline.

        *step_ids* must list every step id belonging to the pipeline in the
        desired order.
        """
        stmt = (
            select(PipelineStep)
            .where(PipelineStep.pipeline_instance_id == pipeline_id)
        )
        result = await self.db.execute(stmt)
        steps_by_id = {s.id: s for s in result.scalars().all()}

        if set(step_ids) != set(steps_by_id.keys()):
            raise ValueError(
                "step_ids must contain exactly the IDs of all steps in the pipeline"
            )

        for order, sid in enumerate(step_ids, start=1):
            steps_by_id[sid].step_order = order

        await self.db.flush()
        return sorted(steps_by_id.values(), key=lambda s: s.step_order)

    async def remove_step(
        self, pipeline_id: uuid.UUID, step_id: uuid.UUID
    ) -> None:
        """Remove a step from a pipeline."""
        stmt = select(PipelineStep).where(
            PipelineStep.id == step_id,
            PipelineStep.pipeline_instance_id == pipeline_id,
        )
        result = await self.db.execute(stmt)
        step = result.scalar_one_or_none()
        if step is None:
            raise ValueError(f"Step {step_id} not found in pipeline {pipeline_id}")
        await self.db.delete(step)
        await self.db.flush()
        logger.info("Removed step %s from pipeline %s", step_id, pipeline_id)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    async def validate_pipeline(self, pipeline_id: uuid.UUID) -> ValidationResult:
        """Validate that all step references resolve to existing instances."""
        pipeline = await self.get_pipeline(pipeline_id)
        if pipeline is None:
            return ValidationResult(
                valid=False,
                issues=[ValidationIssue(None, None, "ERROR", "Pipeline not found")],
            )

        issues: list[ValidationIssue] = []

        if not pipeline.steps:
            issues.append(
                ValidationIssue(None, None, "ERROR", "Pipeline has no steps")
            )

        for step in pipeline.steps:
            model = _INSTANCE_MODELS.get(step.ref_type)
            if model is None:
                issues.append(
                    ValidationIssue(
                        step.id,
                        step.step_order,
                        "ERROR",
                        f"Unknown ref_type '{step.ref_type}'",
                    )
                )
                continue

            instance = await self.db.get(model, step.ref_id)
            if instance is None:
                issues.append(
                    ValidationIssue(
                        step.id,
                        step.step_order,
                        "ERROR",
                        f"{step.ref_type} instance {step.ref_id} not found",
                    )
                )

        return ValidationResult(valid=len(issues) == 0, issues=issues)

    # ------------------------------------------------------------------
    # Activation / Deactivation
    # ------------------------------------------------------------------

    async def activate_pipeline(
        self, pipeline_id: uuid.UUID, worker_id: str | None = None
    ) -> PipelineActivation:
        """Activate a pipeline, creating a new ``PipelineActivation``."""
        from hermes.domain.services.stage_lifecycle import StageLifecycleManager

        pipeline = await self.get_pipeline(pipeline_id)
        if pipeline is None:
            raise ValueError(f"Pipeline {pipeline_id} not found")

        validation = await self.validate_pipeline(pipeline_id)
        if not validation.valid:
            msgs = "; ".join(i.message for i in validation.issues)
            raise ValueError(f"Pipeline validation failed: {msgs}")

        now = datetime.now(UTC)
        activation = PipelineActivation(
            pipeline_instance_id=pipeline_id,
            status="STARTING",
            started_at=now,
            last_heartbeat_at=now,
            worker_id=worker_id,
        )
        self.db.add(activation)

        pipeline.status = "ACTIVE"
        await self.db.flush()

        # Initialise a RUNNING StageRuntimeState for every enabled step.
        step_ids = [step.id for step in pipeline.steps]
        if step_ids:
            stage_manager = StageLifecycleManager(self.db)
            await stage_manager.initialize_stage_states(activation.id, step_ids)

        logger.info("Activated pipeline %s → activation %s", pipeline_id, activation.id)
        return activation

    async def deactivate_pipeline(self, pipeline_id: uuid.UUID) -> None:
        """Deactivate a pipeline by stopping its latest running activation."""
        stmt = (
            select(PipelineActivation)
            .where(
                PipelineActivation.pipeline_instance_id == pipeline_id,
                PipelineActivation.status.in_(["STARTING", "RUNNING"]),
            )
            .order_by(PipelineActivation.started_at.desc())
        )
        result = await self.db.execute(stmt)
        activation = result.scalar_one_or_none()

        if activation is None:
            raise ValueError(f"No active activation for pipeline {pipeline_id}")

        activation.status = "STOPPED"
        activation.stopped_at = datetime.now(UTC)

        pipeline = await self.db.get(PipelineInstance, pipeline_id)
        if pipeline is not None:
            pipeline.status = "PAUSED"

        await self.db.flush()
        logger.info("Deactivated pipeline %s", pipeline_id)

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    async def get_pipeline_status(self, pipeline_id: uuid.UUID) -> PipelineStatus:
        """Get a status snapshot for a pipeline."""
        pipeline = await self.get_pipeline(pipeline_id)
        if pipeline is None:
            raise ValueError(f"Pipeline {pipeline_id} not found")

        # Find latest activation
        stmt = (
            select(PipelineActivation)
            .where(PipelineActivation.pipeline_instance_id == pipeline_id)
            .order_by(PipelineActivation.started_at.desc())
            .limit(1)
        )
        result = await self.db.execute(stmt)
        activation = result.scalar_one_or_none()

        from hermes.domain.models.execution import WorkItem

        wi_count = 0
        if activation is not None:
            from sqlalchemy import func as sa_func

            stmt_count = select(sa_func.count()).where(
                WorkItem.pipeline_instance_id == pipeline_id
            )
            count_result = await self.db.execute(stmt_count)
            wi_count = count_result.scalar() or 0

        return PipelineStatus(
            pipeline_id=pipeline.id,
            pipeline_name=pipeline.name,
            status=pipeline.status,
            step_count=len(pipeline.steps),
            active_activation_id=activation.id if activation else None,
            activation_status=activation.status if activation else None,
            last_heartbeat_at=activation.last_heartbeat_at if activation else None,
            work_item_count=wi_count,
        )
