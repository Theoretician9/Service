from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery

router = Router(name="artifact")


@router.message(Command("artifacts"))
async def cmd_artifacts(message: Message):
    """Show user's recent artifacts."""
    pass
