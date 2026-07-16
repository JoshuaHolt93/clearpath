from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = Field(default="development", alias="CLEARPATH_ENV")
    database_url: str = Field(default="sqlite:///./clearpath_dev.db", alias="DATABASE_URL")
    secret_key: str = Field(default="dev-secret-change-me", alias="SECRET_KEY")
    session_cookie_name: str = Field(default="clearpath_session", alias="SESSION_COOKIE_NAME")
    session_minutes: int = Field(default=60 * 24 * 14, alias="SESSION_MINUTES")
    pending_session_minutes: int = Field(default=15, alias="PENDING_SESSION_MINUTES")
    stay_signed_in_days: int = Field(default=30, alias="STAY_SIGNED_IN_DAYS")
    mfa_required: bool = Field(default=True, alias="MFA_REQUIRED")
    expose_dev_tokens: bool = Field(default=False, alias="EXPOSE_DEV_TOKENS")
    password_hash_method: str = Field(default="scrypt:32768:8:1", alias="PASSWORD_HASH_METHOD")
    password_reset_token_max_age_seconds: int = Field(default=1800, alias="PASSWORD_RESET_TOKEN_MAX_AGE_SECONDS")
    web_app_url: str | None = Field(default=None, alias="WEB_APP_URL")

    mfa_push_provider: str = Field(default="none", alias="MFA_PUSH_PROVIDER")
    duo_client_id: str | None = Field(default=None, alias="DUO_CLIENT_ID")
    duo_client_secret: str | None = Field(default=None, alias="DUO_CLIENT_SECRET")
    duo_api_hostname: str | None = Field(default=None, alias="DUO_API_HOSTNAME")
    duo_redirect_uri: str | None = Field(default=None, alias="DUO_REDIRECT_URI")

    resend_api_key: str | None = Field(default=None, alias="RESEND_API_KEY")
    transactional_email_from: str | None = Field(default=None, alias="TRANSACTIONAL_EMAIL_FROM")
    mail_server: str | None = Field(default=None, alias="MAIL_SERVER")
    mail_port: int = Field(default=587, alias="MAIL_PORT")
    mail_username: str | None = Field(default=None, alias="MAIL_USERNAME")
    mail_password: str | None = Field(default=None, alias="MAIL_PASSWORD")
    mail_use_tls: bool = Field(default=True, alias="MAIL_USE_TLS")
    mail_use_ssl: bool = Field(default=False, alias="MAIL_USE_SSL")
    mail_default_sender: str | None = Field(default=None, alias="MAIL_DEFAULT_SENDER")

    plaid_token_encryption_key: str | None = Field(default=None, alias="PLAID_TOKEN_ENCRYPTION_KEY")
    customer_data_encryption_key: str | None = Field(default=None, alias="CUSTOMER_DATA_ENCRYPTION_KEY")
    plaid_webhook_secret: str | None = Field(default=None, alias="PLAID_WEBHOOK_SECRET")

    plaid_client_id: str | None = Field(default=None, alias="PLAID_CLIENT_ID")
    plaid_secret: str | None = Field(default=None, alias="PLAID_SECRET")
    plaid_env: str = Field(default="sandbox", alias="PLAID_ENV")
    plaid_products: list[str] = Field(default=["transactions"], alias="PLAID_PRODUCTS")
    plaid_country_codes: list[str] = Field(default=["US"], alias="PLAID_COUNTRY_CODES")
    plaid_redirect_uri: str | None = Field(default=None, alias="PLAID_REDIRECT_URI")
    plaid_webhook_url: str | None = Field(default=None, alias="PLAID_WEBHOOK_URL")
    auto_refresh_plaid_on_page_load: bool = Field(default=True, alias="AUTO_REFRESH_PLAID_ON_PAGE_LOAD")
    plaid_auto_refresh_min_interval_minutes: int = Field(default=15, alias="PLAID_AUTO_REFRESH_MIN_INTERVAL_MINUTES")
    validation_pricing_mode: bool = Field(default=False, alias="VALIDATION_PRICING_MODE")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    google_ai_api_key: str | None = Field(default=None, alias="GOOGLE_AI_API_KEY")
    ai_planner_request_timeout_seconds: int = Field(default=45, alias="AI_PLANNER_REQUEST_TIMEOUT_SECONDS")
    ai_subscription_link_search_timeout_seconds: int = Field(
        default=45,
        alias="AI_SUBSCRIPTION_LINK_SEARCH_TIMEOUT_SECONDS",
    )
    ai_planner_daily_request_limit: int = Field(default=50, alias="AI_PLANNER_DAILY_REQUEST_LIMIT")
    ai_planner_monthly_request_limit: int = Field(default=300, alias="AI_PLANNER_MONTHLY_REQUEST_LIMIT")
    ai_planner_burst_request_limit: int = Field(default=8, alias="AI_PLANNER_BURST_REQUEST_LIMIT")
    ai_planner_burst_window_minutes: int = Field(default=10, alias="AI_PLANNER_BURST_WINDOW_MINUTES")
    ai_planner_monthly_cost_limit_cents: int = Field(default=250, alias="AI_PLANNER_MONTHLY_COST_LIMIT_CENTS")
    ai_planner_default_input_cents_per_million: int = Field(
        default=100,
        alias="AI_PLANNER_DEFAULT_INPUT_CENTS_PER_MILLION",
    )
    ai_planner_default_output_cents_per_million: int = Field(
        default=500,
        alias="AI_PLANNER_DEFAULT_OUTPUT_CENTS_PER_MILLION",
    )
    app_timezone: str | None = Field(default=None, alias="APP_TIMEZONE")

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    @property
    def is_testing(self) -> bool:
        return self.app_env.lower() == "testing"


@lru_cache
def get_settings() -> Settings:
    return Settings()
