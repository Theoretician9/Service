import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        Enum("active", "archived", name="project_status"), default="active"
    )

    # ProjectProfile fields
    goal_statement: Mapped[str | None] = mapped_column(Text)
    success_metrics: Mapped[dict | None] = mapped_column(JSONB)
    constraints: Mapped[dict | None] = mapped_column(JSONB)
    timeline: Mapped[str | None] = mapped_column(String(128))
    chosen_niche: Mapped[str | None] = mapped_column(String(256))
    niche_candidates: Mapped[dict | None] = mapped_column(JSONB)
    hypothesis_table: Mapped[dict | None] = mapped_column(JSONB)
    target_audience: Mapped[dict | None] = mapped_column(JSONB)
    product_description: Mapped[str | None] = mapped_column(Text)
    geography: Mapped[str | None] = mapped_column(String(128))
    budget_range: Mapped[str | None] = mapped_column(String(128))
    business_model: Mapped[str | None] = mapped_column(String(64))
    sales_channels: Mapped[dict | None] = mapped_column(JSONB)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_projects_user_status", "user_id", "status"),
    )
