import structlog
from aiogram.types import Update
from fastapi import APIRouter, Request

from app.config import settings
from app.bot.dispatcher import bot, dp

router = APIRouter()
logger = structlog.get_logger()


@router.post("/webhook/{secret}")
async def webhook(secret: str, request: Request):
    """Telegram webhook endpoint.

    Validates secret token from URL path, feeds update to aiogram dispatcher.
    Always returns HTTP 200 to avoid Telegram retries.
    """
    if secret != settings.telegram_webhook_secret:
        # Still return 200 to not leak info about valid secrets
        logger.warning("webhook_invalid_secret")
        return {"ok": True}

    try:
        data = await request.json()
        update = Update.model_validate(data, context={"bot": bot})
        await dp.feed_update(bot=bot, update=update)
    except Exception:
        logger.exception("webhook_processing_error")

    # Always return 200 within 10 seconds
    return {"ok": True}


async def on_startup():
    """Register webhook with Telegram API on application startup."""
    webhook_url = settings.telegram_webhook_url
    await bot.set_webhook(
        url=webhook_url,
        secret_token=settings.telegram_webhook_secret,
        drop_pending_updates=True,
    )
    logger.info("webhook_registered", url=webhook_url)


async def on_shutdown():
    """Delete webhook and close bot session on shutdown."""
    await bot.delete_webhook()
    await bot.session.close()
    logger.info("webhook_deleted")
