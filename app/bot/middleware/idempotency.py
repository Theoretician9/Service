from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
import structlog

from app.redis_client import redis

logger = structlog.get_logger()


class IdempotencyMiddleware(BaseMiddleware):
    """Deduplicate Telegram updates by update_id in Redis (TTL 24h)."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        update = data.get("event_update")
        if update:
            key = f"processed_update:{update.update_id}"
            if await redis.exists(key):
                logger.info("duplicate_update", update_id=update.update_id)
                return
            await redis.set(key, "ok", ex=86400)
        return await handler(event, data)
