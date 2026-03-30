import structlog
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.config import settings
from app.bot.handlers.onboarding import router as onboarding_router
from app.bot.handlers.main_menu import router as main_menu_router
from app.bot.handlers.message_handler import router as message_router
from app.bot.middleware.auth import AuthMiddleware
from app.bot.middleware.idempotency import IdempotencyMiddleware
from app.bot.middleware.rate_limit import RateLimitMiddleware

logger = structlog.get_logger()

bot = Bot(
    token=settings.telegram_bot_token,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)

dp = Dispatcher()

# Register middleware (order matters: idempotency first, then rate limit, then auth)
dp.message.middleware(IdempotencyMiddleware())
dp.message.middleware(RateLimitMiddleware())
dp.message.middleware(AuthMiddleware())

dp.callback_query.middleware(IdempotencyMiddleware())
dp.callback_query.middleware(RateLimitMiddleware())
dp.callback_query.middleware(AuthMiddleware())

# Register routers (order matters: specific command routers first, catch-all last)
dp.include_router(onboarding_router)
dp.include_router(main_menu_router)
dp.include_router(message_router)
