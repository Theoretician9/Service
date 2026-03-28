import sentry_sdk
import structlog
from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.config import settings
from app.bot.router import router as webhook_router

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_log_level,
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    logger_factory=structlog.stdlib.LoggerFactory(),
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.sentry_dsn:
        sentry_sdk.init(dsn=settings.sentry_dsn, environment=settings.environment)
    yield


app = FastAPI(title="AI Marketplace Bot", version="0.1.0", lifespan=lifespan)
app.include_router(webhook_router)
