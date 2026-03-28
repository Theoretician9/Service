from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
import structlog

from app.redis_client import redis

logger = structlog.get_logger()

RATE_LIMIT = 30  # messages per minute
WINDOW = 60  # seconds


class RateLimitMiddleware(BaseMiddleware):
    """Rate limit: max 30 messages/min per telegram_id."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = getattr(event, "from_user", None)
        if user:
            key = f"rate_limit:{user.id}"
            count = await redis.incr(key)
            if count == 1:
                await redis.expire(key, WINDOW)
            if count > RATE_LIMIT:
                logger.warning("rate_limited", telegram_id=user.id)
                return
        return await handler(event, data)
