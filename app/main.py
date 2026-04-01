import sentry_sdk
import structlog
from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.config import settings
from app.bot.router import router as webhook_router, on_startup, on_shutdown

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
    await on_startup()
    yield
    await on_shutdown()


from pathlib import Path
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="AI Marketplace Bot", version="0.1.0", lifespan=lifespan)
app.include_router(webhook_router)

from app.admin.routes import router as admin_router
app.include_router(admin_router)

# Serve HTML reports as static files
reports_dir = Path(__file__).parent.parent / "reports"
reports_dir.mkdir(exist_ok=True)
app.mount("/reports", StaticFiles(directory=str(reports_dir), html=True), name="reports")
