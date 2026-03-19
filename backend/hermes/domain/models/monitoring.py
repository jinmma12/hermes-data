"""Monitoring layer models - 'What IS running' (activations)."""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from hermes.domain.models.base import Base, TimestampMixin


class PipelineActivation(Base):
    __tablename__ = "pipeline_activations"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid()
    )
    pipeline_instance_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("pipeline_instances.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="STARTING")
    started_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    stopped_at: Mapped[datetime | None] = mapped_column()
    last_heartbeat_at: Mapped[datetime | None] = mapped_column()
    last_polled_at: Mapped[datetime | None] = mapped_column()
    error_message: Mapped[str | None] = mapped_column(Text)
    worker_id: Mapped[str | None] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    pipeline_instance: Mapped["PipelineInstance"] = relationship(  # type: ignore[name-defined]
        back_populates="activations",
    )
    work_items: Mapped[list["WorkItem"]] = relationship(  # type: ignore[name-defined]
        back_populates="pipeline_activation",
    )
    stage_runtime_states: Mapped[list["StageRuntimeState"]] = relationship(
        back_populates="pipeline_activation",
        cascade="all, delete-orphan",
    )


class StageRuntimeState(TimestampMixin, Base):
    """Per-stage runtime lifecycle state for a pipeline activation."""

    __tablename__ = "stage_runtime_states"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid()
    )
    pipeline_activation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("pipeline_activations.id", ondelete="CASCADE"), nullable=False
    )
    pipeline_step_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("pipeline_steps.id", ondelete="CASCADE"), nullable=False
    )
    runtime_status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="RUNNING"
    )
    # Valid runtime_status values: RUNNING, STOPPED, DRAINING, BLOCKED, ERROR
    stopped_at: Mapped[datetime | None] = mapped_column(nullable=True)
    stopped_by: Mapped[str | None] = mapped_column(String(256), nullable=True)
    resumed_at: Mapped[datetime | None] = mapped_column(nullable=True)

    pipeline_activation: Mapped["PipelineActivation"] = relationship(
        back_populates="stage_runtime_states",
    )
    pipeline_step: Mapped["PipelineStep"] = relationship()  # type: ignore[name-defined]
