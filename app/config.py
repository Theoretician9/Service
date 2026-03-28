from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Telegram
    telegram_bot_token: str
    telegram_webhook_secret: str
    telegram_webhook_url: str
    bot_admin_chat_id: int

    # Database
    database_url: str
    database_pool_size: int = 10
    database_max_overflow: int = 20

    # Redis
    redis_url: str = "redis://redis:6379/0"
    celery_broker_url: str = "redis://redis:6379/1"
    celery_result_backend: str = "redis://redis:6379/2"

    # LLM
    anthropic_api_key: str
    openai_api_key: str

    # Search
    tavily_api_key: str

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


settings = Settings()
