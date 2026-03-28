from datetime import datetime

from pydantic import BaseModel


class UserPlanRead(BaseModel):
    plan_type: str
    credits_remaining: int
    credits_monthly_limit: int
    credits_reset_at: datetime
    paid_until: datetime | None

    model_config = {"from_attributes": True}
