import structlog
from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from app.bot.messages import WELCOME, WELCOME_BACK
from app.modules.users.models import User

logger = structlog.get_logger()
router = Router(name="onboarding")


@router.message(CommandStart())
async def cmd_start(message: Message, user: User):
    """Handle /start -- onboarding for new users, welcome back for existing."""
    if not user.onboarding_completed:
        await message.answer(WELCOME)
        logger.info("onboarding_start", telegram_id=user.telegram_id)
    else:
        text = WELCOME_BACK.format(first_name=user.first_name)
        await message.answer(text)
        logger.info("welcome_back", telegram_id=user.telegram_id)
