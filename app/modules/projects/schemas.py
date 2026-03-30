import uuid

from pydantic import BaseModel


class ProjectCreate(BaseModel):
    name: str
    description: str | None = None


class ProjectRead(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    status: str
    goal_statement: str | None
    point_a: str | None
    point_b: str | None
    goal_deadline: str | None
    success_metrics: str | None
    constraints: str | None
    niche_candidates: str | None
    chosen_niche: str | None
    hypothesis_table: str | None
    geography: str | None
    budget_range: str | None
    business_model: str | None

    model_config = {"from_attributes": True}
