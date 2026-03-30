import asyncio
import uuid

import structlog
from sqlalchemy import select

from app.database import async_session
from app.modules.artifacts.models import Artifact, MiniserviceRun
from app.modules.billing.models import UserPlan
from app.modules.users.models import User
from app.miniservices.engine import load_manifest
from app.workers.celery_app import celery_app

logger = structlog.get_logger()

MAX_MESSAGE_LENGTH = 4000


def _format_goal_tree_text(content: dict, summary: str) -> str:
    """Format goal_tree artifact — only SMART goal as text, full report via link."""
    parts = []
    parts.append("🎯 <b>Дерево целей — готово!</b>\n")

    # Extract smart_goal — handle both string and dict
    smart_goal = content.get("smart_goal", "")
    if isinstance(smart_goal, dict):
        smart_goal = smart_goal.get("text", str(smart_goal))
    if smart_goal:
        parts.append(f"📌 <b>SMART-цель:</b>\n{smart_goal}\n")

    point_a = content.get("point_a", "")
    if isinstance(point_a, dict):
        point_a = point_a.get("text", str(point_a))
    point_b = content.get("point_b", "")
    if isinstance(point_b, dict):
        point_b = point_b.get("text", str(point_b))
    deadline = content.get("goal_deadline", "")
    if isinstance(deadline, dict):
        deadline = deadline.get("text", str(deadline))

    if point_a:
        parts.append(f"📍 <b>Где сейчас:</b> {point_a}")
    if point_b:
        parts.append(f"🏁 <b>Куда идём:</b> {point_b}")
    if deadline:
        parts.append(f"📅 <b>Срок:</b> {deadline}")

    return "\n".join(parts)


def _format_artifact_text(artifact_type: str, content, summary: str) -> str:
    """Format artifact content as readable Telegram message."""
    # Handle case where content is stored as string instead of dict
    if isinstance(content, str):
        try:
            content = __import__('json').loads(content)
        except Exception:
            return f"✅ <b>Результат готов!</b>\n\n{summary}"

    if artifact_type == "goal_tree":
        return _format_goal_tree_text(content, summary)

    # Generic fallback for other artifact types
    parts = [f"✅ <b>Результат готов!</b>\n", summary]
    return "\n".join(parts)


def _chunk_text(text: str, max_length: int = MAX_MESSAGE_LENGTH) -> list[str]:
    """Split text into chunks respecting paragraph boundaries."""
    if len(text) <= max_length:
        return [text]

    chunks = []
    current = ""
    paragraphs = text.split("\n\n")

    for paragraph in paragraphs:
        if len(current) + len(paragraph) + 2 > max_length:
            if current:
                chunks.append(current.strip())
                current = ""
            # If single paragraph exceeds limit, split by lines
            if len(paragraph) > max_length:
                lines = paragraph.split("\n")
                for line in lines:
                    if len(current) + len(line) + 1 > max_length:
                        if current:
                            chunks.append(current.strip())
                        current = line + "\n"
                    else:
                        current += line + "\n"
            else:
                current = paragraph + "\n\n"
        else:
            current += paragraph + "\n\n"

    if current.strip():
        chunks.append(current.strip())

    return chunks if chunks else [text[:max_length]]


async def _send_result(run_id: str) -> None:
    """Async implementation: load artifact and send to user."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from app.config import settings as _settings

    _engine = create_async_engine(_settings.database_url, pool_size=2, max_overflow=2)
    _session_factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)

    run_uuid = uuid.UUID(run_id)

    async with _session_factory() as session:
        # Load run
        stmt = select(MiniserviceRun).where(MiniserviceRun.id == run_uuid)
        result = await session.execute(stmt)
        run = result.scalar_one_or_none()
        if not run:
            logger.error("notification_run_not_found", run_id=run_id)
            return

        # Load artifact
        art_stmt = select(Artifact).where(
            Artifact.run_id == run_uuid,
            Artifact.is_current == True,
        )
        art_result = await session.execute(art_stmt)
        artifact = art_result.scalar_one_or_none()
        if not artifact:
            logger.error("notification_artifact_not_found", run_id=run_id)
            return

        # Load user to get telegram_id
        user_stmt = select(User).where(User.id == run.user_id)
        user_result = await session.execute(user_stmt)
        user = user_result.scalar_one_or_none()
        if not user:
            logger.error("notification_user_not_found", user_id=str(run.user_id))
            return

        # Load billing info for credits remaining message
        plan_stmt = select(UserPlan).where(UserPlan.user_id == run.user_id)
        plan_result = await session.execute(plan_stmt)
        plan = plan_result.scalar_one_or_none()

        # Load manifest for credit cost
        manifest = load_manifest(run.miniservice_id)
        credit_cost = manifest.get("credit_cost", 1)

    # Format the result text
    text = _format_artifact_text(
        artifact.artifact_type, artifact.content, artifact.summary
    )

    # Append credits info
    if plan:
        credits_line = (
            f"\n💳 Использовано {credit_cost} кр. "
            f"(остаток: {plan.credits_remaining}/{plan.credits_monthly_limit})"
        )
        text += credits_line

    # Send via bot
    from app.bot.dispatcher import bot
    from app.integrations.html_report import html_report
    from app.config import settings as _settings

    # Send text result (compact — only SMART goal)
    chunks = _chunk_text(text)
    for chunk in chunks:
        await bot.send_message(
            chat_id=user.telegram_id,
            text=chunk,
            parse_mode="HTML",
        )

    # Auto-generate HTML report and send link
    try:
        filename = await html_report.generate(
            artifact.artifact_type, artifact.content, str(run.id)
        )
        if filename:
            report_url = f"https://service1.vps.webdock.cloud/reports/{filename}"
            await bot.send_message(
                chat_id=user.telegram_id,
                text=f"📄 <a href=\"{report_url}\">Открыть полный отчёт</a>",
                parse_mode="HTML",
                disable_web_page_preview=False,
            )
            logger.info("html_report_sent", run_id=run_id, url=report_url)
        else:
            logger.warning("html_report_generation_failed", run_id=run_id)
    except Exception as report_err:
        logger.error("html_report_error", run_id=run_id, error=str(report_err))

    # Credits info
    if plan:
        credits_line = (
            f"💳 Использовано {credit_cost} кр. "
            f"(остаток: {plan.credits_remaining}/{plan.credits_monthly_limit})"
        )
        await bot.send_message(
            chat_id=user.telegram_id,
            text=credits_line,
        )

    logger.info("result_notification_sent", run_id=run_id, telegram_id=user.telegram_id)


async def _send_failure(run_id: str) -> None:
    """Async implementation: notify user about failure."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from app.config import settings as _settings

    _engine = create_async_engine(_settings.database_url, pool_size=2, max_overflow=2)
    _session_factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)

    run_uuid = uuid.UUID(run_id)

    async with _session_factory() as session:
        stmt = select(MiniserviceRun).where(MiniserviceRun.id == run_uuid)
        result = await session.execute(stmt)
        run = result.scalar_one_or_none()
        if not run:
            logger.error("failure_notification_run_not_found", run_id=run_id)
            return

        user_stmt = select(User).where(User.id == run.user_id)
        user_result = await session.execute(user_stmt)
        user = user_result.scalar_one_or_none()
        if not user:
            return

    from app.bot.dispatcher import bot
    from app.bot.messages import ERROR_GENERIC

    await bot.send_message(
        chat_id=user.telegram_id,
        text=ERROR_GENERIC,
        parse_mode="HTML",
    )

    logger.info("failure_notification_sent", run_id=run_id, telegram_id=user.telegram_id)


@celery_app.task
def send_result_notification(run_id: str):
    """Send miniservice result to user via Telegram."""
    logger.info("sending_result", run_id=run_id)
    asyncio.run(_send_result(run_id))


@celery_app.task
def send_failure_notification(run_id: str):
    """Notify user about failed miniservice run."""
    logger.info("sending_failure", run_id=run_id)
    asyncio.run(_send_failure(run_id))
