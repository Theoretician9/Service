import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Integer, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UserPlan(Base):
    __tablename__ = "user_plans"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True, nullable=False)
    plan_type: Mapped[str] = mapped_column(Enum("free", "paid", name="plan_type"), default="free")
    credits_remaining: Mapped[int] = mapped_column(Integer, default=3)
    credits_monthly_limit: Mapped[int] = mapped_column(Integer, default=3)
    credits_reset_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    paid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
