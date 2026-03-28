from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery

router = Router(name="main_menu")


@router.message(Command("menu"))
async def cmd_menu(message: Message):
    """Show main menu."""
    pass


@router.message(Command("help"))
async def cmd_help(message: Message):
    """Show help menu."""
    pass


@router.message(Command("plan"))
async def cmd_plan(message: Message):
    """Show plan info."""
    pass


@router.message(Command("cancel"))
async def cmd_cancel(message: Message):
    """Cancel current miniservice dialog, return to menu."""
    pass


@router.message(Command("delete_account"))
async def cmd_delete_account(message: Message):
    """Request account deletion."""
    pass
