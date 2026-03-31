"""Initial schema

Revision ID: 001
Revises:
Create Date: 2026-03-30
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop all existing types and tables (clean slate — no data in DB yet)
    op.execute("DROP TABLE IF EXISTS bug_reports CASCADE")
    op.execute("DROP TABLE IF EXISTS analytics_events CASCADE")
    op.execute("DROP TABLE IF EXISTS change_proposals CASCADE")
    op.execute("DROP TABLE IF EXISTS artifacts CASCADE")
    op.execute("DROP TABLE IF EXISTS miniservice_runs CASCADE")
    op.execute("DROP TABLE IF EXISTS projects CASCADE")
    op.execute("DROP TABLE IF EXISTS user_plans CASCADE")
    op.execute("DROP TABLE IF EXISTS users CASCADE")
    op.execute("DROP TYPE IF EXISTS plan_type CASCADE")
    op.execute("DROP TYPE IF EXISTS project_status CASCADE")
    op.execute("DROP TYPE IF EXISTS run_mode CASCADE")
    op.execute("DROP TYPE IF EXISTS run_status CASCADE")
    op.execute("DROP TYPE IF EXISTS proposal_status CASCADE")

    # Create enum types
    op.execute("CREATE TYPE plan_type AS ENUM ('free', 'paid')")
    op.execute("CREATE TYPE project_status AS ENUM ('active', 'archived')")
    op.execute("CREATE TYPE run_mode AS ENUM ('sequential', 'standalone')")
    op.execute("CREATE TYPE run_status AS ENUM ('collecting', 'processing', 'completed', 'failed', 'partially_completed')")
    op.execute("CREATE TYPE proposal_status AS ENUM ('pending', 'accepted', 'rejected')")

    # Users
    op.execute("""
        CREATE TABLE users (
            id UUID PRIMARY KEY,
            telegram_id BIGINT UNIQUE NOT NULL,
            username VARCHAR(64),
            first_name VARCHAR(128) NOT NULL,
            language_code VARCHAR(8) DEFAULT 'ru',
            onboarding_completed BOOLEAN DEFAULT false,
            onboarding_role VARCHAR(64),
            onboarding_primary_goal VARCHAR(512),
            is_blocked BOOLEAN DEFAULT false,
            deleted_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX ix_users_telegram_id ON users (telegram_id)")

    # User Plans
    op.execute("""
        CREATE TABLE user_plans (
            id UUID PRIMARY KEY,
            user_id UUID UNIQUE NOT NULL REFERENCES users(id),
            plan_type plan_type DEFAULT 'free',
            credits_remaining INTEGER DEFAULT 3,
            credits_monthly_limit INTEGER DEFAULT 3,
            credits_reset_at TIMESTAMPTZ NOT NULL,
            paid_until TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now()
        )
    """)

    # Projects
    op.execute("""
        CREATE TABLE projects (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users(id),
            name VARCHAR(128) NOT NULL,
            description TEXT,
            status project_status DEFAULT 'active',
            goal_statement TEXT,
            point_a TEXT,
            point_b TEXT,
            goal_deadline VARCHAR(128),
            success_metrics JSONB,
            constraints JSONB,
            niche_candidates JSONB,
            chosen_niche VARCHAR(256),
            hypothesis_table JSONB,
            geography VARCHAR(128),
            budget_range VARCHAR(128),
            business_model VARCHAR(64),
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX ix_projects_user_id ON projects (user_id)")
    op.execute("CREATE INDEX ix_projects_user_status ON projects (user_id, status)")

    # Miniservice Runs
    op.execute("""
        CREATE TABLE miniservice_runs (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users(id),
            project_id UUID NOT NULL REFERENCES projects(id),
            miniservice_id VARCHAR(64) NOT NULL,
            mode run_mode NOT NULL,
            status run_status NOT NULL,
            collected_fields JSONB NOT NULL DEFAULT '{}',
            celery_task_id VARCHAR(255),
            error_message TEXT,
            credits_spent INTEGER DEFAULT 0,
            llm_tokens_used INTEGER DEFAULT 0,
            web_searches_used INTEGER DEFAULT 0,
            started_at TIMESTAMPTZ DEFAULT now(),
            completed_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX ix_runs_user_id ON miniservice_runs (user_id)")
    op.execute("CREATE INDEX ix_runs_project_id ON miniservice_runs (project_id)")
    op.execute("CREATE INDEX ix_runs_user_status ON miniservice_runs (user_id, status)")
    op.execute("CREATE INDEX ix_runs_project_miniservice ON miniservice_runs (project_id, miniservice_id)")

    # Artifacts
    op.execute("""
        CREATE TABLE artifacts (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users(id),
            project_id UUID NOT NULL REFERENCES projects(id),
            run_id UUID NOT NULL REFERENCES miniservice_runs(id),
            miniservice_id VARCHAR(64) NOT NULL,
            artifact_type VARCHAR(64) NOT NULL,
            artifact_schema_version VARCHAR(16) NOT NULL DEFAULT '1.0',
            title VARCHAR(256) NOT NULL,
            version INTEGER DEFAULT 1,
            is_current BOOLEAN DEFAULT true,
            is_outdated BOOLEAN DEFAULT false,
            content JSONB NOT NULL,
            summary TEXT NOT NULL,
            google_sheets_url VARCHAR(512),
            created_at TIMESTAMPTZ DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX ix_artifacts_user_id ON artifacts (user_id)")
    op.execute("CREATE INDEX ix_artifacts_project_id ON artifacts (project_id)")
    op.execute("CREATE INDEX ix_artifacts_user_current ON artifacts (user_id, is_current)")
    op.execute("CREATE INDEX ix_artifacts_project_current ON artifacts (project_id, is_current)")
    op.execute("CREATE INDEX ix_artifacts_user_ms_current ON artifacts (user_id, miniservice_id, is_current)")

    # Change Proposals
    op.execute("""
        CREATE TABLE change_proposals (
            id UUID PRIMARY KEY,
            project_id UUID NOT NULL REFERENCES projects(id),
            run_id UUID NOT NULL REFERENCES miniservice_runs(id),
            proposed_changes JSONB NOT NULL,
            conflict_fields JSONB NOT NULL,
            affected_artifact_ids JSONB NOT NULL,
            explanation TEXT NOT NULL,
            status proposal_status DEFAULT 'pending',
            created_at TIMESTAMPTZ DEFAULT now(),
            resolved_at TIMESTAMPTZ
        )
    """)
    op.execute("CREATE INDEX ix_proposals_project_id ON change_proposals (project_id)")
    op.execute("CREATE INDEX ix_proposals_project_status ON change_proposals (project_id, status)")

    # Analytics Events
    op.execute("""
        CREATE TABLE analytics_events (
            id UUID PRIMARY KEY,
            user_id UUID,
            event_type VARCHAR(64) NOT NULL,
            properties JSONB DEFAULT '{}',
            created_at TIMESTAMPTZ DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX ix_events_user_id ON analytics_events (user_id)")
    op.execute("CREATE INDEX ix_events_event_type ON analytics_events (event_type)")
    op.execute("CREATE INDEX ix_events_created_at ON analytics_events (created_at)")
    op.execute("CREATE INDEX ix_events_type_created ON analytics_events (event_type, created_at)")
    op.execute("CREATE INDEX ix_events_user_type ON analytics_events (user_id, event_type)")

    # Bug Reports
    op.execute("""
        CREATE TABLE bug_reports (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users(id),
            text TEXT NOT NULL,
            created_at TIMESTAMPTZ DEFAULT now()
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS bug_reports CASCADE")
    op.execute("DROP TABLE IF EXISTS analytics_events CASCADE")
    op.execute("DROP TABLE IF EXISTS change_proposals CASCADE")
    op.execute("DROP TABLE IF EXISTS artifacts CASCADE")
    op.execute("DROP TABLE IF EXISTS miniservice_runs CASCADE")
    op.execute("DROP TABLE IF EXISTS projects CASCADE")
    op.execute("DROP TABLE IF EXISTS user_plans CASCADE")
    op.execute("DROP TABLE IF EXISTS users CASCADE")
    op.execute("DROP TYPE IF EXISTS proposal_status")
    op.execute("DROP TYPE IF EXISTS run_status")
    op.execute("DROP TYPE IF EXISTS run_mode")
    op.execute("DROP TYPE IF EXISTS project_status")
    op.execute("DROP TYPE IF EXISTS plan_type")
