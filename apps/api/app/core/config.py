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
    mfa_required: bool = Field(default=True, alias="MFA_REQUIRED")
    expose_dev_tokens: bool = Field(default=False, alias="EXPOSE_DEV_TOKENS")
    password_hash_method: str = Field(default="scrypt:32768:8:1", alias="PASSWORD_HASH_METHOD")

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
