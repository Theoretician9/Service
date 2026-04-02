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
from app.logging_config import get_conversation_logger

logger = structlog.get_logger()
conv_logger = get_conversation_logger()

MAX_MESSAGE_LENGTH = 4000


def _safe_str(val) -> str:
    """Extract string from value that might be dict or other type."""
    if isinstance(val, dict):
        return val.get("text", str(val))
    return str(val) if val else ""


def _format_goal_tree_text(content: dict, summary: str) -> str:
    """Format goal_tree artifact — SMART summary + pointer to full report."""
    parts = []
    parts.append("🎯 <b>Дерево целей — готово!</b>\n")

    smart_goal = _safe_str(content.get("smart_goal"))
    if smart_goal:
        parts.append(f"📌 <b>SMART-цель:</b>\n{smart_goal}\n")

    point_a = _safe_str(content.get("point_a"))
    point_b = _safe_str(content.get("point_b"))
    deadline = _safe_str(content.get("goal_deadline"))
    motivation = _safe_str(content.get("real_motivation"))
    metrics = content.get("success_metrics", [])

    if point_a:
        parts.append(f"📍 <b>Где сейчас:</b> {point_a}")
    if point_b:
        parts.append(f"🏁 <b>Куда идём:</b> {point_b}")
    if deadline:
        parts.append(f"📅 <b>Срок:</b> {deadline}")
    if motivation:
        parts.append(f"💡 <b>Мотивация:</b> {motivation}")
    if metrics and isinstance(metrics, list):
        metrics_str = "; ".join(str(m) for m in metrics[:3])
        parts.append(f"📊 <b>Критерии успеха:</b> {metrics_str}")

    parts.append("\n📄 Полный отчёт с планом действий, рисками и ограничениями — в файле ниже.")

    return "\n".join(parts)


def _format_niche_table_text(content: dict, summary: str) -> str:
    """Format niche_table artifact — compact 10-niche selection summary."""
    parts = []
    parts.append("🔍 <b>Выбор ниши — готово!</b>\n")

    recommended_niche = _safe_str(content.get("recommended_niche"))
    if recommended_niche:
        parts.append(f"📌 <b>Рекомендованная:</b> {recommended_niche}")

    recommendation = _safe_str(content.get("recommendation"))
    if recommendation:
        trimmed = recommendation[:200]
        if len(recommendation) > 200:
            trimmed += "…"
        parts.append(trimmed)

    # Top-5 niches with scores
    top_niches = content.get("top_niches", [])
    if top_niches:
        parts.append("\n🏆 <b>Топ-5:</b>")
        for i, niche in enumerate(top_niches[:5], start=1):
            name = _safe_str(niche.get("name"))
            scores = niche.get("scores", {})
            total = scores.get("total", "?") if isinstance(scores, dict) else "?"
            parts.append(f"{i}. {name} — {total}/25")

    parts.append(
        "\n📋 Ещё 5 направлений + подробная декомпозиция, "
        "числовая модель и план тестирования — в отчёте ниже."
    )

    return "\n".join(parts)


NEXT_STEP_MAP = {
    "goal_setting": {
        "recommended": "niche_selection",
        "recommended_name": "Выбор ниши",
        "recommended_cost": 2,
        "text": (
            "📍 Следующий логичный шаг — выбор ниши и декомпозиция.\n"
            "Я проанализирую рынок, подберу подходящие ниши и разложу лучшую по полочкам.\n\n"
            "Напиши «давай» чтобы перейти к выбору ниши.\n"
            "Или выбери другой инструмент:\n"
            "• Поиск поставщиков (2 кр.)\n"
            "• Скрипты продаж (2 кр.)\n"
            "• Продающие объявления (2 кр.)\n"
            "• Поиск клиентов (3 кр., Paid)"
        ),
    },
    "niche_selection": {
        "recommended": "supplier_search",
        "recommended_name": "Поиск поставщиков",
        "recommended_cost": 2,
        "text": (
            "📍 Следующий шаг — найти поставщиков для выбранной ниши.\n"
            "Я поищу реальных поставщиков, сравню условия и подготовлю шаблоны писем.\n\n"
            "Напиши «давай» чтобы начать поиск поставщиков.\n"
            "Или выбери другой инструмент:\n"
            "• Скрипты продаж (2 кр.)\n"
            "• Продающие объявления (2 кр.)\n"
            "• Поиск клиентов (3 кр., Paid)"
        ),
    },
    "supplier_search": {
        "text": (
            "📍 Что дальше?\n"
            "• Скрипты продаж — напишу готовые скрипты для твоего продукта (2 кр.)\n"
            "• Продающие объявления — создам тексты для площадок (2 кр.)\n"
            "• Поиск клиентов — найду потенциальных покупателей (3 кр., Paid)\n\n"
            "Напиши что нужно."
        ),
    },
    "sales_scripts": {
        "text": (
            "📍 Что дальше?\n"
            "• Продающие объявления (2 кр.)\n"
            "• Поиск клиентов (3 кр., Paid)\n\n"
            "Напиши что нужно."
        ),
    },
    "ad_creation": {
        "text": (
            "📍 Что дальше?\n"
            "• Поиск клиентов — найду потенциальных покупателей (3 кр., Paid)\n"
            "• Скрипты продаж (2 кр.)\n\n"
            "Напиши что нужно."
        ),
    },
    "lead_search": {
        "text": "✅ Все основные инструменты пройдены! Можешь запустить любой повторно или создать новый проект.",
    },
}


def _get_next_step_suggestion(miniservice_id: str) -> str:
    """Get suggestion text for next step after miniservice completion."""
    step = NEXT_STEP_MAP.get(miniservice_id, {})
    return step.get("text", "Напиши что хочешь сделать дальше.")


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

    if artifact_type == "niche_table":
        return _format_niche_table_text(content, summary)

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

    # Format the result text (no credits — sent separately)
    text = _format_artifact_text(
        artifact.artifact_type, artifact.content, artifact.summary
    )

    # Create a fresh bot instance for worker (don't reuse app's bot — different event loop)
    from aiogram import Bot
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode
    from app.config import settings as _s
    from app.integrations.html_report import html_report

    bot = Bot(token=_s.telegram_bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))

    # Send text result (compact — only SMART goal)
    chunks = _chunk_text(text)
    for chunk in chunks:
        await bot.send_message(
            chat_id=user.telegram_id,
            text=chunk,
            parse_mode="HTML",
        )

    # Auto-generate HTML report and send as file
    try:
        filename = await html_report.generate(
            artifact.artifact_type, artifact.content, str(run.id)
        )
        if filename:
            from pathlib import Path
            from aiogram.types import FSInputFile
            file_path = Path("/app/reports") / filename
            if file_path.exists():
                doc = FSInputFile(str(file_path), filename=f"{artifact.title}.html")
                await bot.send_document(
                    chat_id=user.telegram_id,
                    document=doc,
                    caption="📄 Полный отчёт",
                )
                logger.info("html_report_sent", run_id=run_id)
            else:
                logger.warning("html_report_file_not_found", path=str(file_path))
        else:
            logger.warning("html_report_generation_failed", run_id=run_id)
    except Exception as report_err:
        logger.error("html_report_error", run_id=run_id, error=str(report_err))

    # Credits + next step suggestion
    credits_text = ""
    if plan:
        credits_text = (
            f"💳 Использовано {credit_cost} кр. "
            f"(остаток: {plan.credits_remaining}/{plan.credits_monthly_limit})\n\n"
        )

    # Suggest next logical step based on completed miniservice
    next_step = _get_next_step_suggestion(run.miniservice_id)
    await bot.send_message(
        chat_id=user.telegram_id,
        text=credits_text + next_step,
    )

    await bot.session.close()
    logger.info("result_notification_sent", run_id=run_id, telegram_id=user.telegram_id)

    conv_logger.info(
        "notification_sent",
        run_id=run_id,
        telegram_id=user.telegram_id,
        user_name=user.first_name,
        artifact_type=artifact.artifact_type,
        miniservice_id=run.miniservice_id,
        notification_type="result",
    )


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

    from aiogram import Bot
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode
    from app.bot.messages import ERROR_GENERIC

    bot = Bot(token=_settings.telegram_bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))

    await bot.send_message(
        chat_id=user.telegram_id,
        text=ERROR_GENERIC,
        parse_mode="HTML",
    )

    await bot.session.close()
    logger.info("failure_notification_sent", run_id=run_id, telegram_id=user.telegram_id)

    conv_logger.info(
        "notification_sent",
        run_id=run_id,
        telegram_id=user.telegram_id,
        user_name=user.first_name,
        miniservice_id=run.miniservice_id,
        notification_type="failure",
    )


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
