import structlog
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.messages import CANCEL_CONFIRMED
from app.modules.users.models import User
from app.modules.billing.service import BillingService
from app.modules.projects.service import ProjectService
from app.redis_client import redis

logger = structlog.get_logger()
router = Router(name="main_menu")

HELP_TEXT = (
    "<b>Доступные команды:</b>\n\n"
    "/start — начать работу с ботом\n"
    "/menu — главное меню\n"
    "/projects — мои проекты\n"
    "/plan — информация о тарифе\n"
    "/cancel — отменить текущую операцию\n"
    "/help — показать эту справку\n"
    "/delete_account — удалить аккаунт\n\n"
    "Или просто напиши, чем хочешь заняться, и я помогу."
)

MENU_TEXT = (
    "Выбери, чем займёмся:\n\n"
    "1. 🎯 Постановка цели\n"
    "2. 🔍 Подбор ниши\n"
    "3. 📦 Поиск поставщиков\n"
    "4. 💬 Скрипты продаж\n"
    "5. 📢 Создание объявлений\n"
    "6. 👥 Поиск клиентов\n\n"
    "Или просто опиши задачу своими словами."
)

DELETE_CONFIRM_TEXT = (
    "⚠️ Вы уверены, что хотите удалить аккаунт?\n"
    "Все проекты и результаты будут потеряны.\n\n"
    "Для подтверждения отправьте: /delete_account_confirm"
)


@router.message(Command("menu"))
async def cmd_menu(message: Message, user: User):
    """Show main menu."""
    await message.answer(MENU_TEXT)


@router.message(Command("help"))
async def cmd_help(message: Message, user: User):
    """Show help menu."""
    await message.answer(HELP_TEXT)


@router.message(Command("plan"))
async def cmd_plan(message: Message, user: User, db_session: AsyncSession):
    """Show plan info."""
    billing_service = BillingService(db_session)
    plan = await billing_service.get_plan(user.id)

    if plan is None:
        await message.answer(
            "📋 <b>Тариф:</b> Free\n"
            "💰 <b>Кредиты:</b> 3/3\n\n"
            "Используй /start для начала работы."
        )
        return

    plan_name = "Paid" if plan.plan_type == "paid" else "Free"
    reset_date = plan.credits_reset_at.strftime("%d.%m.%Y")

    text = (
        f"📋 <b>Тариф:</b> {plan_name}\n"
        f"💰 <b>Кредиты:</b> {plan.credits_remaining}/{plan.credits_monthly_limit}\n"
        f"🔄 <b>Сброс:</b> {reset_date}\n"
    )

    if plan.plan_type == "paid" and plan.paid_until:
        paid_until = plan.paid_until.strftime("%d.%m.%Y")
        text += f"💎 <b>Оплачено до:</b> {paid_until}\n"

    await message.answer(text)


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, user: User):
    """Cancel current miniservice dialog, return to menu."""
    dialog_key = f"dialog:{user.telegram_id}"
    deleted = await redis.delete(dialog_key)

    if deleted:
        logger.info("dialog_cancelled", telegram_id=user.telegram_id)

    await message.answer(CANCEL_CONFIRMED)


@router.message(Command("projects"))
async def cmd_projects(message: Message, user: User, db_session: AsyncSession):
    """List user projects."""
    project_service = ProjectService(db_session)
    projects = await project_service.get_user_projects(user.id)

    if not projects:
        await message.answer(
            "📁 У тебя пока нет проектов.\n"
            "Отправь /start, чтобы создать первый."
        )
        return

    lines = ["📁 <b>Твои проекты:</b>\n"]
    for i, project in enumerate(projects, 1):
        lines.append(f"{i}. {project.name}")

    await message.answer("\n".join(lines))


@router.message(Command("delete_account"))
async def cmd_delete_account(message: Message, user: User):
    """Request account deletion."""
    await message.answer(DELETE_CONFIRM_TEXT)
