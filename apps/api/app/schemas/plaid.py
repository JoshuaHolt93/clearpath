from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PlaidStatusResponse(BaseModel):
    ready: bool
    sdk_installed: bool
    crypto_installed: bool
    has_credentials: bool
    has_encryption_key: bool
    environment: str


class PlaidLinkTokenResponse(BaseModel):
    link_token: str
    consent_token: str


class PlaidExchangePublicTokenRequest(BaseModel):
    public_token: str
    metadata: dict = Field(default_factory=dict)
    consent_token: str | None = None


class AccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    account_type: str
    institution: str | None = None
    current_balance: float
    cash_projection_role: str
    is_manual: bool
    plaid_account_id: str | None = None
    plaid_item_id: int | None = None
    mask: str | None = None


class PlaidIgnoredAccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    plaid_item_id: int | None = None
    plaid_account_id: str
    account_name: str | None = None
    institution_name: str | None = None


class PlaidItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    institution_name: str | None = None
    institution_id: str | None = None
    status: str
    last_synced_at: datetime | None = None
    error_code: str | None = None
    error_message: str | None = None
    consent_acknowledged_at: datetime | None = None
    reconnect_required_at: datetime | None = None
    disconnected_at: datetime | None = None
    accounts: list[AccountResponse] = Field(default_factory=list)


class PlaidItemListResponse(BaseModel):
    items: list[PlaidItemResponse]
    ignored_accounts: list[PlaidIgnoredAccountResponse]


class PlaidItemSyncResponse(BaseModel):
    added: int
    modified: int
    removed: int


class PlaidItemDisconnectResponse(BaseModel):
    disconnected: bool
    already_disconnected: bool


class PlaidRefreshStaleRequest(BaseModel):
    min_interval_minutes: int | None = None


class PlaidRefreshSummaryResponse(BaseModel):
    synced: int
    errors: list[str]


class PlaidLinkEventRequest(BaseModel):
    event_name: str | None = None
    event: str | None = None
    error: dict | None = None
    metadata: dict | None = None


class PlaidLinkEventResponse(BaseModel):
    ok: bool = True


class AccountRemoveResponse(BaseModel):
    removed: bool
    ignored_account_id: int


class AccountCashProjectionRoleUpdateRequest(BaseModel):
    cash_projection_role: str = Field(pattern="^(auto|include|exclude)$")


class AccountTypeUpdateRequest(BaseModel):
    account_type: str
