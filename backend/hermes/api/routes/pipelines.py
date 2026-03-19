"""API routes for Pipeline management (Layer 2+3)."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hermes.domain.models.monitoring import PipelineActivation
from hermes.domain.models.pipeline import PipelineInstance, PipelineStep
from hermes.domain.services.pipeline_manager import PipelineManager
from hermes.domain.services.stage_lifecycle import StageLifecycleManager
from hermes.infrastructure.database.session import get_db

router = APIRouter(prefix="/api/v1/pipelines", tags=["pipelines"])


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class PipelineCreate(BaseModel):
    name: str = Field(..., max_length=256)
    description: str | None = None
    monitoring_type: str = Field(..., max_length=32)
    monitoring_config: dict[str, Any] = Field(default_factory=dict)


class PipelineUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    monitoring_type: str | None = None
    monitoring_config: dict[str, Any] | None = None


class PipelineOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None = None
    monitoring_type: str | None = None
    monitoring_config: dict[str, Any]
    status: str
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class StepCreate(BaseModel):
    step_type: str = Field(..., max_length=20)
    ref_type: str = Field(..., max_length=20)
    ref_id: uuid.UUID
    step_order: int | None = None
    on_error: str = "STOP"
    retry_count: int = 0
    retry_delay_seconds: int = 5


class StepUpdate(BaseModel):
    is_enabled: bool | None = None
    on_error: str | None = None
    retry_count: int | None = None
    retry_delay_seconds: int | None = None


class StepOut(BaseModel):
    id: uuid.UUID
    pipeline_instance_id: uuid.UUID
    step_order: int
    step_type: str
    ref_type: str
    ref_id: uuid.UUID
    is_enabled: bool
    on_error: str
    retry_count: int
    retry_delay_seconds: int

    model_config = {"from_attributes": True}


class StepReorder(BaseModel):
    step_ids: list[uuid.UUID]


class ActivationOut(BaseModel):
    id: uuid.UUID
    pipeline_instance_id: uuid.UUID
    status: str
    started_at: str
    stopped_at: str | None = None
    last_heartbeat_at: str | None = None
    last_polled_at: str | None = None
    error_message: str | None = None
    worker_id: str | None = None

    model_config = {"from_attributes": True}


class PipelineStatusOut(BaseModel):
    pipeline_id: uuid.UUID
    pipeline_name: str
    status: str
    step_count: int
    active_activation_id: uuid.UUID | None = None
    activation_status: str | None = None
    last_heartbeat_at: str | None = None
    work_item_count: int = 0


class ValidationOut(BaseModel):
    valid: bool
    issues: list[dict[str, Any]]


# ---------------------------------------------------------------------------
# Pipeline CRUD
# ---------------------------------------------------------------------------


@router.get("/", response_model=list[PipelineOut])
async def list_pipelines(
    db: AsyncSession = Depends(get_db),
) -> Any:
    """List all pipelines."""
    stmt = select(PipelineInstance).order_by(PipelineInstance.created_at.desc())
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("/", response_model=PipelineOut, status_code=status.HTTP_201_CREATED)
async def create_pipeline(
    body: PipelineCreate,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Create a new pipeline."""
    mgr = PipelineManager(db)
    pipeline = await mgr.create_pipeline(
        name=body.name,
        monitoring_type=body.monitoring_type,
        monitoring_config=body.monitoring_config,
        description=body.description,
    )
    return pipeline


@router.get("/{pipeline_id}", response_model=PipelineOut)
async def get_pipeline(
    pipeline_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Get a pipeline by ID."""
    mgr = PipelineManager(db)
    pipeline = await mgr.get_pipeline(pipeline_id)
    if pipeline is None:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    return pipeline


@router.put("/{pipeline_id}", response_model=PipelineOut)
async def update_pipeline(
    pipeline_id: uuid.UUID,
    body: PipelineUpdate,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Update pipeline metadata."""
    pipeline = await db.get(PipelineInstance, pipeline_id)
    if pipeline is None:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    if body.name is not None:
        pipeline.name = body.name
    if body.description is not None:
        pipeline.description = body.description
    if body.monitoring_type is not None:
        pipeline.monitoring_type = body.monitoring_type
    if body.monitoring_config is not None:
        pipeline.monitoring_config = body.monitoring_config

    await db.flush()
    return pipeline


# ---------------------------------------------------------------------------
# Pipeline Steps
# ---------------------------------------------------------------------------


@router.get("/{pipeline_id}/steps", response_model=list[StepOut])
async def list_steps(
    pipeline_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """List all steps in a pipeline."""
    stmt = (
        select(PipelineStep)
        .where(PipelineStep.pipeline_instance_id == pipeline_id)
        .order_by(PipelineStep.step_order)
    )
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post(
    "/{pipeline_id}/steps",
    response_model=StepOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_step(
    pipeline_id: uuid.UUID,
    body: StepCreate,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Add a step to the pipeline."""
    mgr = PipelineManager(db)
    pipeline = await mgr.get_pipeline(pipeline_id)
    if pipeline is None:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    step = await mgr.add_step(
        pipeline_id=pipeline_id,
        step_type=body.step_type,
        ref_type=body.ref_type,
        ref_id=body.ref_id,
        step_order=body.step_order,
    )
    # Apply optional fields
    step.on_error = body.on_error
    step.retry_count = body.retry_count
    step.retry_delay_seconds = body.retry_delay_seconds
    await db.flush()
    return step


@router.put("/{pipeline_id}/steps/{step_id}", response_model=StepOut)
async def update_step(
    pipeline_id: uuid.UUID,
    step_id: uuid.UUID,
    body: StepUpdate,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Update a pipeline step."""
    stmt = select(PipelineStep).where(
        PipelineStep.id == step_id,
        PipelineStep.pipeline_instance_id == pipeline_id,
    )
    result = await db.execute(stmt)
    step = result.scalar_one_or_none()
    if step is None:
        raise HTTPException(status_code=404, detail="Step not found")

    if body.is_enabled is not None:
        step.is_enabled = body.is_enabled
    if body.on_error is not None:
        step.on_error = body.on_error
    if body.retry_count is not None:
        step.retry_count = body.retry_count
    if body.retry_delay_seconds is not None:
        step.retry_delay_seconds = body.retry_delay_seconds

    await db.flush()
    return step


@router.delete("/{pipeline_id}/steps/{step_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_step(
    pipeline_id: uuid.UUID,
    step_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Remove a step from a pipeline."""
    mgr = PipelineManager(db)
    try:
        await mgr.remove_step(pipeline_id, step_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.put("/{pipeline_id}/steps/reorder", response_model=list[StepOut])
async def reorder_steps(
    pipeline_id: uuid.UUID,
    body: StepReorder,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Reorder the steps in a pipeline."""
    mgr = PipelineManager(db)
    try:
        steps = await mgr.reorder_steps(pipeline_id, body.step_ids)
        return steps
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ---------------------------------------------------------------------------
# Pipeline Lifecycle
# ---------------------------------------------------------------------------


@router.post("/{pipeline_id}/activate", response_model=ActivationOut)
async def activate_pipeline(
    pipeline_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Activate a pipeline (start monitoring)."""
    mgr = PipelineManager(db)
    try:
        activation = await mgr.activate_pipeline(pipeline_id)
        return activation
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/{pipeline_id}/deactivate", status_code=status.HTTP_200_OK)
async def deactivate_pipeline(
    pipeline_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Deactivate a pipeline (stop monitoring)."""
    mgr = PipelineManager(db)
    try:
        await mgr.deactivate_pipeline(pipeline_id)
        return {"status": "deactivated"}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/{pipeline_id}/activations", response_model=list[ActivationOut])
async def list_activations(
    pipeline_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """List activation history for a pipeline."""
    stmt = (
        select(PipelineActivation)
        .where(PipelineActivation.pipeline_instance_id == pipeline_id)
        .order_by(PipelineActivation.started_at.desc())
    )
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/{pipeline_id}/status", response_model=PipelineStatusOut)
async def get_pipeline_status(
    pipeline_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Get current status of a pipeline."""
    mgr = PipelineManager(db)
    try:
        status_obj = await mgr.get_pipeline_status(pipeline_id)
        return status_obj
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


# ---------------------------------------------------------------------------
# Stage Runtime Control
# ---------------------------------------------------------------------------


class StageRuntimeOut(BaseModel):
    pipeline_activation_id: uuid.UUID
    pipeline_step_id: uuid.UUID
    runtime_status: str
    stopped_at: str | None = None
    stopped_by: str | None = None
    resumed_at: str | None = None

    model_config = {"from_attributes": True}


class StageStopRequest(BaseModel):
    stopped_by: str = "operator"
    reason: str | None = None


class StageQueueOut(BaseModel):
    stage_id: uuid.UUID
    stage_order: int
    stage_type: str
    runtime_status: str
    queued_count: int = 0
    in_flight_count: int = 0
    completed_count: int = 0


async def _validate_activation_ownership(
    db: AsyncSession, pipeline_id: uuid.UUID, activation_id: uuid.UUID
) -> PipelineActivation:
    """Verify activation belongs to the pipeline."""
    activation = await db.get(PipelineActivation, activation_id)
    if activation is None:
        raise HTTPException(status_code=404, detail="Activation not found")
    if activation.pipeline_instance_id != pipeline_id:
        raise HTTPException(
            status_code=400,
            detail=f"Activation {activation_id} does not belong to pipeline {pipeline_id}",
        )
    return activation


@router.get(
    "/{pipeline_id}/activations/{activation_id}/stages/runtime",
    response_model=list[StageRuntimeOut],
)
async def get_stage_runtime_states(
    pipeline_id: uuid.UUID,
    activation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Get runtime states for all stages in an activation."""
    await _validate_activation_ownership(db, pipeline_id, activation_id)
    from hermes.domain.models.monitoring import StageRuntimeState

    stmt = select(StageRuntimeState).where(
        StageRuntimeState.pipeline_activation_id == activation_id
    )
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post(
    "/{pipeline_id}/activations/{activation_id}/stages/{stage_id}/stop",
    response_model=StageRuntimeOut,
)
async def stop_stage(
    pipeline_id: uuid.UUID,
    activation_id: uuid.UUID,
    stage_id: uuid.UUID,
    body: StageStopRequest | None = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Stop a stage runtime — prevents dispatch into this stage."""
    await _validate_activation_ownership(db, pipeline_id, activation_id)

    stopped_by = body.stopped_by if body else "operator"
    lifecycle = StageLifecycleManager(db)
    try:
        state = await lifecycle.stop_stage(activation_id, stage_id, stopped_by=stopped_by)
        return state
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post(
    "/{pipeline_id}/activations/{activation_id}/stages/{stage_id}/resume",
    response_model=StageRuntimeOut,
)
async def resume_stage(
    pipeline_id: uuid.UUID,
    activation_id: uuid.UUID,
    stage_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Resume a stopped stage runtime."""
    await _validate_activation_ownership(db, pipeline_id, activation_id)

    lifecycle = StageLifecycleManager(db)
    try:
        state = await lifecycle.resume_stage(activation_id, stage_id)
        return state
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get(
    "/{pipeline_id}/activations/{activation_id}/queues",
    response_model=list[StageQueueOut],
)
async def get_queue_summary(
    pipeline_id: uuid.UUID,
    activation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Get queue depth summary for all stages in an activation."""
    await _validate_activation_ownership(db, pipeline_id, activation_id)

    lifecycle = StageLifecycleManager(db)
    summaries = await lifecycle.get_queue_summary(activation_id)
    return [
        StageQueueOut(
            stage_id=s.stage_id,
            stage_order=s.stage_order,
            stage_type=s.stage_type,
            runtime_status=s.runtime_status,
            queued_count=s.queued_count,
            in_flight_count=s.in_flight_count,
            completed_count=s.completed_count,
        )
        for s in summaries
    ]
