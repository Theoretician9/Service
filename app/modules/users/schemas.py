import uuid
from datetime import datetime

from pydantic import BaseModel


class UserCreate(BaseModel):
    telegram_id: int
    username: str | None = None
    first_name: str
    language_code: str = "ru"


class UserRead(BaseModel):
    id: uuid.UUID
    telegram_id: int
    username: str | None
    first_name: str
    onboarding_completed: bool
    onboarding_role: str | None
    onboarding_primary_goal: str | None
    is_blocked: bool
    deleted_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}
