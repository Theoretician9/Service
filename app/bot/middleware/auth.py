from typing import Any, Awaitable, Callable, Dict

import structlog
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from app.database import async_session
from app.modules.billing.service import BillingService
from app.modules.users.service import UserService

logger = structlog.get_logger()


class AuthMiddleware(BaseMiddleware):
    """Find or create User by telegram_id from update.

    Stores user in data["user"] and db session in data["db_session"]
    so handlers can access them directly.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        tg_user = data.get("event_from_user")
        if tg_user is None:
            # No user context (e.g. channel posts) — skip auth
            return await handler(event, data)

        async with async_session() as session:
            user_service = UserService(session)
            user = await user_service.get_or_create(
                telegram_id=tg_user.id,
                first_name=tg_user.first_name or "User",
                username=tg_user.username,
            )

            # Ensure billing plan exists
            billing_service = BillingService(session)
            await billing_service.get_or_create_plan(user.id)

            if user.is_blocked:
                logger.warning("blocked_user_attempt", telegram_id=tg_user.id)
                return

            data["user"] = user
            data["db_session"] = session

            return await handler(event, data)
