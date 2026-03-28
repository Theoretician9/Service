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
    chosen_niche: str | None

    model_config = {"from_attributes": True}
