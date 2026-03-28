from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject


class AuthMiddleware(BaseMiddleware):
    """Find or create User by telegram_id from update."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        # TODO: lookup/create user by telegram_id, add to data["user"]
        return await handler(event, data)
