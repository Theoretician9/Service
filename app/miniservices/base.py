from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any
import uuid


@dataclass
class MiniserviceContext:
    run_id: uuid.UUID
    user_id: uuid.UUID
    project_id: uuid.UUID | None
    miniservice_id: str
    collected_fields: dict[str, Any]
    project_profile: dict[str, Any] | None


@dataclass
class MiniserviceResult:
    artifact_type: str
    title: str
    content: dict[str, Any]
    summary: str
    llm_tokens_used: int = 0
    web_searches_used: int = 0


class MiniserviceBase(ABC):
    """Base class for all miniservice implementations."""

    @abstractmethod
    async def execute(self, ctx: MiniserviceContext) -> MiniserviceResult:
        """Execute the miniservice and return the result artifact."""
        ...
