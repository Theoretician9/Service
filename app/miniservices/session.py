import json
import uuid
from typing import Any

from app.redis_client import redis

DIALOG_TTL = 86400  # 24 hours


async def get_dialog(telegram_user_id: int) -> dict | None:
    """Get current dialog state from Redis."""
    key = f"dialog:{telegram_user_id}"
    data = await redis.get(key)
    if data:
        return json.loads(data)
    return None


async def set_dialog(
    telegram_user_id: int,
    miniservice_id: str,
    run_id: uuid.UUID,
    project_id: uuid.UUID | None = None,
    mode: str = "quick",
    step: int = 1,
    collected_fields: dict[str, Any] | None = None,
) -> None:
    """Create or update dialog state in Redis."""
    key = f"dialog:{telegram_user_id}"
    data = {
        "miniservice_id": miniservice_id,
        "run_id": str(run_id),
        "step": step,
        "collected_fields": collected_fields or {},
        "project_id": str(project_id) if project_id else None,
        "mode": mode,
    }
    await redis.set(key, json.dumps(data), ex=DIALOG_TTL)


async def update_dialog_field(telegram_user_id: int, field_id: str, value: Any) -> dict:
    """Add a collected field to dialog state. Returns updated dialog."""
    dialog = await get_dialog(telegram_user_id)
    if dialog is None:
        raise ValueError("No active dialog")
    dialog["collected_fields"][field_id] = value
    dialog["step"] += 1
    key = f"dialog:{telegram_user_id}"
    await redis.set(key, json.dumps(dialog), ex=DIALOG_TTL)
    return dialog


async def clear_dialog(telegram_user_id: int) -> None:
    """Clear dialog state."""
    key = f"dialog:{telegram_user_id}"
    await redis.delete(key)
