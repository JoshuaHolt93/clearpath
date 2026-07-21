from __future__ import annotations

import json
from functools import lru_cache
from typing import Annotated, Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


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
    force_https: bool = Field(default=False, alias="FORCE_HTTPS")
    session_cookie_secure: bool = Field(default=False, alias="SESSION_COOKIE_SECURE")

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
    # NoDecode: Flask reads these as comma-separated strings (app/__init__.py:1339-1340),
    # so skip pydantic-settings' default JSON decoding and split the same way.
    plaid_products: Annotated[list[str], NoDecode] = Field(default=["transactions"], alias="PLAID_PRODUCTS")
    plaid_country_codes: Annotated[list[str], NoDecode] = Field(default=["US"], alias="PLAID_COUNTRY_CODES")
    plaid_redirect_uri: str | None = Field(default=None, alias="PLAID_REDIRECT_URI")
    plaid_webhook_url: str | None = Field(default=None, alias="PLAID_WEBHOOK_URL")
    auto_refresh_plaid_on_page_load: bool = Field(default=True, alias="AUTO_REFRESH_PLAID_ON_PAGE_LOAD")
    plaid_auto_refresh_min_interval_minutes: int = Field(default=15, alias="PLAID_AUTO_REFRESH_MIN_INTERVAL_MINUTES")
    validation_pricing_mode: bool = Field(default=False, alias="VALIDATION_PRICING_MODE")
    billing_enabled: bool = Field(default=False, alias="BILLING_ENABLED")
    stripe_secret_key: str | None = Field(default=None, alias="STRIPE_SECRET_KEY")
    stripe_webhook_secret: str | None = Field(default=None, alias="STRIPE_WEBHOOK_SECRET")
    stripe_basic_price_id: str | None = Field(default=None, alias="STRIPE_BASIC_PRICE_ID")
    stripe_plus_price_id: str | None = Field(default=None, alias="STRIPE_PLUS_PRICE_ID")
    stripe_premium_price_id: str | None = Field(default=None, alias="STRIPE_PREMIUM_PRICE_ID")
    stripe_at_cost_price_id: str | None = Field(default=None, alias="STRIPE_AT_COST_PRICE_ID")
    stripe_free_price_id: str | None = Field(default=None, alias="STRIPE_FREE_PRICE_ID")
    stripe_price_id: str | None = Field(default=None, alias="STRIPE_PRICE_ID")
    stripe_trial_period_days: int = Field(default=0, alias="STRIPE_TRIAL_PERIOD_DAYS")
    stripe_plan_currency: str | None = Field(default=None, alias="STRIPE_PLAN_CURRENCY")
    stripe_plan_interval: str | None = Field(default=None, alias="STRIPE_PLAN_INTERVAL")
    stripe_plan_amount_cents: str | None = Field(default=None, alias="STRIPE_PLAN_AMOUNT_CENTS")
    stripe_plan_name: str | None = Field(default=None, alias="STRIPE_PLAN_NAME")
    stripe_cancellation_terms: str | None = Field(default=None, alias="STRIPE_CANCELLATION_TERMS")
    stripe_basic_plan_amount_cents: str | None = Field(default=None, alias="STRIPE_BASIC_PLAN_AMOUNT_CENTS")
    stripe_basic_plan_name: str | None = Field(default=None, alias="STRIPE_BASIC_PLAN_NAME")
    stripe_plus_plan_amount_cents: str | None = Field(default=None, alias="STRIPE_PLUS_PLAN_AMOUNT_CENTS")
    stripe_plus_plan_name: str | None = Field(default=None, alias="STRIPE_PLUS_PLAN_NAME")
    stripe_premium_plan_amount_cents: str | None = Field(default=None, alias="STRIPE_PREMIUM_PLAN_AMOUNT_CENTS")
    stripe_premium_plan_name: str | None = Field(default=None, alias="STRIPE_PREMIUM_PLAN_NAME")
    stripe_success_url: str | None = Field(default=None, alias="STRIPE_SUCCESS_URL")
    stripe_cancel_url: str | None = Field(default=None, alias="STRIPE_CANCEL_URL")
    stripe_portal_return_url: str | None = Field(default=None, alias="STRIPE_PORTAL_RETURN_URL")
    free_tier_signups_enabled: bool = Field(default=False, alias="FREE_TIER_SIGNUPS_ENABLED")
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

    @field_validator("database_url", mode="after")
    @classmethod
    def _normalize_postgres_driver(cls, value: str) -> str:
        """Pin Postgres URLs to the psycopg 3 dialect.

        Hosting providers (Railway, Heroku, Render) hand out `postgresql://` or
        the legacy `postgres://`. SQLAlchemy maps both to psycopg2, which this
        project does not depend on, so the app would die with
        `ModuleNotFoundError: psycopg2`. An explicit `+driver` is left alone.
        """
        for prefix in ("postgresql://", "postgres://"):
            if value.startswith(prefix):
                return "postgresql+psycopg://" + value[len(prefix) :]
        return value

    @field_validator("plaid_products", "plaid_country_codes", mode="before")
    @classmethod
    def _split_csv(cls, value: Any) -> Any:
        """Parse comma-separated env values the way Flask does.

        Flask: `[p.strip() for p in os.getenv(...).split(",") if p.strip()]`.
        A JSON array is still accepted so existing list defaults keep working.
        """
        if not isinstance(value, str):
            return value
        stripped = value.strip()
        if stripped.startswith("["):
            try:
                return json.loads(stripped)
            except json.JSONDecodeError:
                pass
        return [item.strip() for item in stripped.split(",") if item.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    @property
    def is_testing(self) -> bool:
        return self.app_env.lower() == "testing"


@lru_cache
def get_settings() -> Settings:
    return Settings()
