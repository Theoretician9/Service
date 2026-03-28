from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery

router = Router(name="project")


@router.message(Command("projects"))
async def cmd_projects(message: Message):
    """Show user's projects list."""
    pass
