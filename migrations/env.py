from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app.config import Settings
from app.database import Base

# Import all models so they are registered with Base.metadata
from app.modules.users.models import User  # noqa: F401
from app.modules.projects.models import Project  # noqa: F401
from app.modules.artifacts.models import MiniserviceRun, Artifact, ChangeProposal  # noqa: F401
from app.modules.billing.models import UserPlan  # noqa: F401
from app.modules.analytics.models import AnalyticsEvent, BugReport  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    """Get database URL from settings, replacing asyncpg with psycopg2 for sync Alembic."""
    settings = Settings()
    url = settings.database_url
    return url.replace("+asyncpg", "+psycopg2")


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = create_engine(
        get_url(),
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
