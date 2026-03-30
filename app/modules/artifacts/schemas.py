import uuid
from datetime import datetime

from pydantic import BaseModel


class ArtifactRead(BaseModel):
    id: uuid.UUID
    miniservice_id: str
    artifact_type: str
    title: str
    version: int
    is_current: bool
    is_outdated: bool
    summary: str
    artifact_schema_version: str
    google_sheets_url: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
