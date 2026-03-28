from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

router = Router(name="onboarding")


@router.message(CommandStart())
async def cmd_start(message: Message):
    """Handle /start — onboarding for new users, main menu for existing."""
    pass
