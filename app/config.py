from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Telegram
    telegram_bot_token: str
    telegram_webhook_secret: str
    telegram_webhook_url: str
    bot_admin_chat_ids: str = ""  # comma-separated telegram IDs

    @property
    def admin_ids(self) -> list[int]:
        if not self.bot_admin_chat_ids:
            return []
        return [int(x.strip()) for x in self.bot_admin_chat_ids.split(",") if x.strip()]

    def is_admin(self, telegram_id: int) -> bool:
        return telegram_id in self.admin_ids

    # Database
    database_url: str
    database_pool_size: int = 10
    database_max_overflow: int = 20

    # Redis
    redis_url: str = "redis://redis:6379/0"
    celery_broker_url: str = "redis://redis:6379/1"
    celery_result_backend: str = "redis://redis:6379/2"

    # LLM
    anthropic_api_key: str = ""
    anthropic_api_keys: str = ""  # comma-separated additional Anthropic API keys
    openai_api_key: str = ""

    @property
    def all_anthropic_keys(self) -> list[str]:
        """Return list of all Anthropic API keys (main + additional)."""
        keys = []
        if self.anthropic_api_key:
            keys.append(self.anthropic_api_key)
        if self.anthropic_api_keys:
            keys.extend(k.strip() for k in self.anthropic_api_keys.split(",") if k.strip())
        return keys

    # Search
    tavily_api_key: str = ""

    # Google Sheets
    google_service_account_json: str = ""
    google_service_account_email: str = ""

    # Monitoring
    sentry_dsn: str = ""
    environment: str = "development"
    log_level: str = "INFO"

    # Billing
    free_plan_monthly_credits: int = 3
    paid_plan_monthly_credits: int = 30
    paid_plan_price_rub: int = 990
    max_projects_free: int = 2
    max_projects_paid: int = 20

    # Timezone
    tz: str = "Europe/Moscow"

    # Limits
    llm_request_timeout_seconds: int = 60
    max_message_length: int = 4000

    # Orchestrator
    orchestrator_history_messages: int = 20
    orchestrator_confidence_threshold: float = 0.85

    # Mentor
    mentor_max_fallback_attempts: int = 3

    # Admin dashboard
    admin_username: str = "admin"
    admin_password: str = "admin123"

    # Goal reality filter thresholds
    goal_max_ratio_1_month: int = 10
    goal_max_ratio_3_months: int = 20
    goal_max_ratio_6_months: int = 50
    goal_max_ratio_12_months: int = 100
    goal_max_corrections: int = 3


settings = Settings()
