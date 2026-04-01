import structlog
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.messages import CANCEL_CONFIRMED
from app.config import settings
from app.modules.users.models import User
from app.modules.billing.service import BillingService
from app.modules.projects.service import ProjectService
from app.modules.artifacts.models import MiniserviceRun, Artifact
from app.redis_client import redis
from sqlalchemy import delete as sa_delete, select

logger = structlog.get_logger()
router = Router(name="main_menu")

HELP_TEXT = (
    "<b>Доступные команды:</b>\n\n"
    "/start — начать работу с ботом\n"
    "/menu — главное меню\n"
    "/projects — мои проекты\n"
    "/plan — информация о тарифе\n"
    "/cancel — отменить текущую операцию\n"
    "/reset — сбросить свои данные и начать заново\n"
    "/wipe_all — удалить ВСЕ данные (только для админов)\n"
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


@router.message(Command("wipe_all"))
async def cmd_wipe_all(message: Message, user: User, db_session: AsyncSession):
    """Admin command: wipe ALL users data. Full DB reset without migrations."""
    if not settings.is_admin(user.telegram_id):
        await message.answer("Эта команда доступна только администраторам.")
        return

    from app.modules.projects.models import Project
    from app.modules.artifacts.models import ChangeProposal
    from app.modules.analytics.models import AnalyticsEvent, BugReport
    from app.modules.billing.models import UserPlan

    await db_session.execute(sa_delete(ChangeProposal))
    await db_session.execute(sa_delete(Artifact))
    await db_session.execute(sa_delete(MiniserviceRun))
    await db_session.execute(sa_delete(AnalyticsEvent))
    await db_session.execute(sa_delete(BugReport))
    await db_session.execute(sa_delete(Project))
    await db_session.execute(sa_delete(UserPlan))
    await db_session.execute(sa_delete(User))
    await db_session.commit()

    # Flush Redis
    await redis.flushall()

    await message.answer("💣 Все данные всех пользователей удалены. /start для начала.")
    logger.info("admin_wipe_all", telegram_id=user.telegram_id)


@router.message(Command("reset"))
async def cmd_reset(message: Message, user: User, db_session: AsyncSession):
    """Reset own data: wipe projects, artifacts, runs for current user."""

    # Clear Redis
    for key_prefix in ["dialog:", "active_project:", "conversation:", "extracted_fields:", "pending_confirmation:", "dep_chain:"]:
        await redis.delete(f"{key_prefix}{user.telegram_id}")

    # Delete artifacts, runs, projects from DB
    from app.modules.projects.models import Project
    from app.modules.analytics.models import AnalyticsEvent, BugReport

    projects = await db_session.execute(select(Project.id).where(Project.user_id == user.id))
    project_ids = [row[0] for row in projects.all()]

    if project_ids:
        await db_session.execute(sa_delete(Artifact).where(Artifact.project_id.in_(project_ids)))
        await db_session.execute(sa_delete(MiniserviceRun).where(MiniserviceRun.project_id.in_(project_ids)))
        from app.modules.artifacts.models import ChangeProposal
        await db_session.execute(sa_delete(ChangeProposal).where(ChangeProposal.project_id.in_(project_ids)))
        await db_session.execute(sa_delete(Project).where(Project.id.in_(project_ids)))

    # Reset onboarding
    user.onboarding_completed = False
    user.onboarding_role = None
    user.onboarding_primary_goal = None

    # Reset credits to monthly limit
    billing_service = BillingService(db_session)
    plan = await billing_service.get_or_create_plan(user.id)
    plan.credits_remaining = plan.credits_monthly_limit
    await db_session.commit()

    await message.answer(f"🔄 Все данные сброшены. Кредиты восстановлены: {plan.credits_remaining}/{plan.credits_monthly_limit}.\nНапиши /start чтобы начать заново.")
    logger.info("admin_reset", telegram_id=user.telegram_id)


@router.message(Command("delete_account"))
async def cmd_delete_account(message: Message, user: User):
    """Request account deletion."""
    await message.answer(DELETE_CONFIRM_TEXT)
