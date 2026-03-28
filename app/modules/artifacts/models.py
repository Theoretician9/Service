import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class MiniserviceRun(Base):
    __tablename__ = "miniservice_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    miniservice_id: Mapped[str] = mapped_column(String(64), nullable=False)
    mode: Mapped[str] = mapped_column(Enum("quick", "project", name="run_mode"), nullable=False)
    status: Mapped[str] = mapped_column(
        Enum(
            "collecting", "processing", "completed", "failed", "partially_completed",
            name="run_status",
        ),
        nullable=False,
    )
    collected_fields: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    celery_task_id: Mapped[str | None] = mapped_column(String(255))
    error_message: Mapped[str | None] = mapped_column(Text)
    credits_spent: Mapped[int] = mapped_column(Integer, default=0)
    llm_tokens_used: Mapped[int] = mapped_column(Integer, default=0)
    web_searches_used: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_runs_user_status", "user_id", "status"),
        Index("ix_runs_project_miniservice", "project_id", "miniservice_id"),
    )


class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    miniservice_id: Mapped[str] = mapped_column(String(64), nullable=False)
    artifact_type: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    is_outdated: Mapped[bool] = mapped_column(Boolean, default=False)
    content: Mapped[dict] = mapped_column(JSONB, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    google_sheets_url: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_artifacts_user_current", "user_id", "is_current"),
        Index("ix_artifacts_project_current", "project_id", "is_current"),
        Index("ix_artifacts_user_ms_current", "user_id", "miniservice_id", "is_current"),
    )


class ChangeProposal(Base):
    __tablename__ = "change_proposals"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    proposed_changes: Mapped[dict] = mapped_column(JSONB, nullable=False)
    conflict_fields: Mapped[dict] = mapped_column(JSONB, nullable=False)
    affected_artifact_ids: Mapped[dict] = mapped_column(JSONB, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        Enum("pending", "accepted", "rejected", name="proposal_status"), default="pending"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_proposals_project_status", "project_id", "status"),
    )
