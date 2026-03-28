from fastapi import APIRouter, Request, HTTPException
import structlog

from app.config import settings

router = APIRouter()
logger = structlog.get_logger()


@router.post("/webhook")
async def webhook(request: Request):
    """Telegram webhook endpoint. Validates secret token, feeds update to aiogram dispatcher."""
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if secret != settings.telegram_webhook_secret:
        raise HTTPException(status_code=403, detail="Invalid secret token")

    data = await request.json()
    # TODO: feed to aiogram dispatcher
    return {"ok": True}
