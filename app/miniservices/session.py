import json
import uuid
from typing import Any

from app.redis_client import redis

DIALOG_TTL = 86400  # 24 hours
EXTRACTED_FIELDS_TTL = 7200  # 2 hours
PENDING_CONFIRMATION_TTL = 600  # 10 minutes
DEP_CHAIN_TTL = 86400  # 24 hours
ACTIVE_PROJECT_TTL = 604800  # 7 days
CONVERSATION_TTL = 604800  # 7 days


async def get_dialog(telegram_user_id: int) -> dict | None:
    """Get current dialog state from Redis."""
    key = f"dialog:{telegram_user_id}"
    data = await redis.get(key)
    if data:
        dialog = json.loads(data)
        dialog.setdefault("short_answer_count", 0)
        return dialog
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
        "short_answer_count": 0,
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


# ── Extracted Fields ─────────────────────────────────────────────────


async def get_extracted_fields(telegram_user_id: int) -> dict:
    """Get extracted fields mapping {miniservice_id: {field_id: value}}."""
    key = f"extracted_fields:{telegram_user_id}"
    data = await redis.get(key)
    if data:
        return json.loads(data)
    return {}


async def set_extracted_fields(telegram_user_id: int, fields: dict) -> None:
    """Merge fields into existing extracted fields.

    ``fields`` is ``{miniservice_id: {field_id: value}}``.
    Existing miniservice entries are updated (merged), not replaced.
    """
    key = f"extracted_fields:{telegram_user_id}"
    existing = await get_extracted_fields(telegram_user_id)
    for ms_id, field_map in fields.items():
        if ms_id in existing:
            existing[ms_id].update(field_map)
        else:
            existing[ms_id] = field_map
    await redis.set(key, json.dumps(existing), ex=EXTRACTED_FIELDS_TTL)


async def clear_extracted_fields(telegram_user_id: int) -> None:
    """Delete extracted fields."""
    key = f"extracted_fields:{telegram_user_id}"
    await redis.delete(key)


# ── Pending Confirmation ─────────────────────────────────────────────


async def get_pending_confirmation(telegram_user_id: int) -> dict | None:
    """Get pending OrchestratorDecision as dict, or None."""
    key = f"pending_confirmation:{telegram_user_id}"
    data = await redis.get(key)
    if data:
        return json.loads(data)
    return None


async def set_pending_confirmation(telegram_user_id: int, decision: dict) -> None:
    """Store an OrchestratorDecision for user confirmation."""
    key = f"pending_confirmation:{telegram_user_id}"
    await redis.set(key, json.dumps(decision), ex=PENDING_CONFIRMATION_TTL)


async def clear_pending_confirmation(telegram_user_id: int) -> None:
    """Delete pending confirmation."""
    key = f"pending_confirmation:{telegram_user_id}"
    await redis.delete(key)


# ── Dependency Chain ─────────────────────────────────────────────────


async def get_dep_chain(telegram_user_id: int) -> dict | None:
    """Get dependency chain {target_miniservice, chain, project_id}."""
    key = f"dep_chain:{telegram_user_id}"
    data = await redis.get(key)
    if data:
        return json.loads(data)
    return None


async def set_dep_chain(
    telegram_user_id: int,
    target: str,
    chain: list,
    project_id: str,
) -> None:
    """Store a dependency chain for sequential miniservice execution."""
    key = f"dep_chain:{telegram_user_id}"
    data = {
        "target_miniservice": target,
        "chain": chain,
        "project_id": project_id,
    }
    await redis.set(key, json.dumps(data), ex=DEP_CHAIN_TTL)


async def pop_next_from_chain(telegram_user_id: int) -> str | None:
    """Pop the first miniservice id from the chain.

    Returns the popped id or None if chain is empty / doesn't exist.
    Deletes the key when the chain becomes empty.
    """
    key = f"dep_chain:{telegram_user_id}"
    data = await redis.get(key)
    if not data:
        return None
    chain_data = json.loads(data)
    chain = chain_data.get("chain", [])
    if not chain:
        await redis.delete(key)
        return None
    next_id = chain.pop(0)
    if not chain:
        await redis.delete(key)
    else:
        chain_data["chain"] = chain
        ttl = await redis.ttl(key)
        if ttl < 0:
            ttl = DEP_CHAIN_TTL
        await redis.set(key, json.dumps(chain_data), ex=ttl)
    return next_id


async def clear_dep_chain(telegram_user_id: int) -> None:
    """Delete dependency chain."""
    key = f"dep_chain:{telegram_user_id}"
    await redis.delete(key)


# ── Active Project ───────────────────────────────────────────────────


async def get_active_project(telegram_user_id: int) -> dict | None:
    """Get active project {project_id, project_name}."""
    key = f"active_project:{telegram_user_id}"
    data = await redis.get(key)
    if data:
        return json.loads(data)
    return None


async def set_active_project(
    telegram_user_id: int,
    project_id: str,
    project_name: str,
) -> None:
    """Set the user's active project."""
    key = f"active_project:{telegram_user_id}"
    data = {
        "project_id": project_id,
        "project_name": project_name,
    }
    await redis.set(key, json.dumps(data), ex=ACTIVE_PROJECT_TTL)


# ── Conversation History ─────────────────────────────────────────────


async def get_conversation(
    telegram_user_id: int,
    limit: int = 20,
) -> list[dict]:
    """Get last ``limit`` messages from conversation history."""
    key = f"conversation:{telegram_user_id}"
    data = await redis.get(key)
    if data:
        messages = json.loads(data)
        return messages[-limit:]
    return []


async def append_conversation(
    telegram_user_id: int,
    role: str,
    content: str,
) -> None:
    """Append a message to conversation history."""
    key = f"conversation:{telegram_user_id}"
    data = await redis.get(key)
    messages = json.loads(data) if data else []
    messages.append({"role": role, "content": content})
    await redis.set(key, json.dumps(messages), ex=CONVERSATION_TTL)


async def clear_conversation(telegram_user_id: int) -> None:
    """Delete conversation history."""
    key = f"conversation:{telegram_user_id}"
    await redis.delete(key)
