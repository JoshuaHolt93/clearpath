from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, date, datetime
from typing import Callable

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.plaid_policy import assert_plaid_data_purpose, redact_plaid_sensitive_data
from app.models import (
    Account,
    Category,
    PlaidAccountIgnore,
    PlaidItem,
    PlaidWebhookEvent,
    SubscriptionTransactionIgnore,
    Transaction,
    User,
    utc_now,
)
from app.services.transaction_service import (
    CREDIT_CARD_PAYMENT_CATEGORY_NAME,
    DEFAULT_CATEGORY_TARGETS,
    apply_category_rules,
    build_import_hash,
    looks_like_credit_card_payment,
    merge_duplicate_transactions_for_user,
    normalize_text,
)

try:
    from cryptography.fernet import Fernet, InvalidToken
except ImportError:  # pragma: no cover - exercised after optional dependency install
    Fernet = None
    InvalidToken = Exception

try:
    import plaid
    from plaid.api import plaid_api
    from plaid.model.accounts_get_request import AccountsGetRequest
    from plaid.model.country_code import CountryCode
    from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
    from plaid.model.item_remove_request import ItemRemoveRequest
    from plaid.model.link_token_create_request import LinkTokenCreateRequest
    from plaid.model.link_token_transactions import LinkTokenTransactions
    from plaid.model.products import Products
    from plaid.model.transactions_sync_request import TransactionsSyncRequest
    from plaid.model.transactions_sync_request_options import TransactionsSyncRequestOptions
except ImportError:  # pragma: no cover - exercised after optional dependency install
    plaid = None
    plaid_api = None
    AccountsGetRequest = None
    CountryCode = None
    ItemPublicTokenExchangeRequest = None
    ItemRemoveRequest = None
    LinkTokenCreateRequest = None
    LinkTokenTransactions = None
    Products = None
    TransactionsSyncRequest = None
    TransactionsSyncRequestOptions = None

logger = logging.getLogger(__name__)


class PlaidConfigurationError(RuntimeError):
    pass


class PlaidRequestError(RuntimeError):
    pass


SYNCABLE_PLAID_STATUSES = {"connected"}
RECONNECT_REQUIRED_CODES = {"ITEM_LOGIN_REQUIRED"}
TRANSACTION_UPDATE_WEBHOOK_CODES = {
    "DEFAULT_UPDATE",
    "HISTORICAL_UPDATE",
    "INITIAL_UPDATE",
    "SYNC_UPDATES_AVAILABLE",
    "TRANSACTIONS_REMOVED",
}
DEPOSITORY_BALANCE_TYPES = {
    "cash",
    "cash management",
    "cash_management",
    "checking",
    "depository",
    "limited purpose checking",
    "money market",
    "money_market",
    "prepaid",
    "savings",
}

# Post-sync hooks. Flask calls scan_and_sync_subscriptions (Phase 2c) and
# sync_monthly_plan (Phase 3) after successful syncs; those phases register
# callables here so the call sites stay faithful without forward imports.
POST_SYNC_HOOKS: list[Callable[[Session, User], None]] = []


def run_post_sync_hooks(db: Session, user: User) -> None:
    for hook in POST_SYNC_HOOKS:
        hook(db, user)


def _authorize_plaid_use(purpose: str, *, data_kind: str | None = None):
    approved_purpose = assert_plaid_data_purpose(purpose)
    if data_kind:
        assert_plaid_data_purpose(approved_purpose)
    return approved_purpose


def _raise_plaid_error(exc: Exception) -> None:
    body = getattr(exc, "body", None)
    reason = getattr(exc, "reason", None)
    message = redact_plaid_sensitive_data(str(body or reason or exc))
    raise PlaidRequestError(f"Plaid request failed: {message}") from exc


def plaid_is_ready() -> bool:
    settings = get_settings()
    return bool(plaid and Fernet and settings.plaid_client_id and settings.plaid_secret and settings.plaid_token_encryption_key)


def plaid_status() -> dict:
    settings = get_settings()
    return {
        "ready": plaid_is_ready(),
        "sdk_installed": bool(plaid),
        "crypto_installed": bool(Fernet),
        "has_credentials": bool(settings.plaid_client_id and settings.plaid_secret),
        "has_encryption_key": bool(settings.plaid_token_encryption_key),
        "environment": settings.plaid_env,
    }


def _require_plaid_ready() -> None:
    if not plaid_is_ready():
        status = plaid_status()
        missing = []
        if not status["sdk_installed"]:
            missing.append("plaid-python")
        if not status["crypto_installed"]:
            missing.append("cryptography")
        if not status["has_credentials"]:
            missing.append("PLAID_CLIENT_ID / PLAID_SECRET")
        if not status["has_encryption_key"]:
            missing.append("PLAID_TOKEN_ENCRYPTION_KEY")
        raise PlaidConfigurationError(f"Plaid is not ready yet. Missing: {', '.join(missing)}.")


def _fernet() -> Fernet:
    key = get_settings().plaid_token_encryption_key
    if not key:
        raise PlaidConfigurationError("PLAID_TOKEN_ENCRYPTION_KEY is required before storing Plaid access tokens.")
    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except Exception as exc:
        raise PlaidConfigurationError("PLAID_TOKEN_ENCRYPTION_KEY must be a valid Fernet key.") from exc


def encrypt_access_token(access_token: str) -> str:
    _require_plaid_ready()
    return _fernet().encrypt(access_token.encode()).decode()


def decrypt_access_token(encrypted_access_token: str) -> str:
    _require_plaid_ready()
    if not encrypted_access_token:
        raise PlaidConfigurationError("Stored Plaid access token is not available.")
    try:
        return _fernet().decrypt(encrypted_access_token.encode()).decode()
    except InvalidToken as exc:
        raise PlaidConfigurationError("Stored Plaid access token could not be decrypted.") from exc


def plaid_client():
    _require_plaid_ready()
    settings = get_settings()
    environment_name = settings.plaid_env.lower()
    environments = {
        "sandbox": plaid.Environment.Sandbox,
        "production": plaid.Environment.Production,
    }
    if environment_name not in environments:
        raise PlaidConfigurationError("PLAID_ENV must be sandbox or production.")

    configuration = plaid.Configuration(
        host=environments[environment_name],
        api_key={
            "clientId": settings.plaid_client_id,
            "secret": settings.plaid_secret,
        },
    )
    return plaid_api.PlaidApi(plaid.ApiClient(configuration))


def create_link_token(user: User, *, purpose: str = "account_sync") -> str:
    _authorize_plaid_use(purpose, data_kind="link_token")
    settings = get_settings()
    client = plaid_client()
    products = [Products(product) for product in settings.plaid_products]
    country_codes = [CountryCode(code) for code in settings.plaid_country_codes]
    request_kwargs = {
        "products": products,
        "client_name": "ClearPath Finance",
        "country_codes": country_codes,
        "language": "en",
        "user": {"client_user_id": str(user.id)},
        "transactions": LinkTokenTransactions(days_requested=730),
    }
    if settings.plaid_redirect_uri:
        request_kwargs["redirect_uri"] = settings.plaid_redirect_uri
    if settings.plaid_webhook_url:
        request_kwargs["webhook"] = settings.plaid_webhook_url

    try:
        response = client.link_token_create(LinkTokenCreateRequest(**request_kwargs))
    except Exception as exc:
        _raise_plaid_error(exc)
    return response["link_token"]


def exchange_public_token(
    db: Session,
    user: User,
    public_token: str,
    metadata: dict | None = None,
    *,
    purpose: str = "account_sync",
    consent_acknowledged_at: datetime | None = None,
) -> PlaidItem:
    _authorize_plaid_use(purpose, data_kind="public_token")
    client = plaid_client()
    try:
        response = client.item_public_token_exchange(ItemPublicTokenExchangeRequest(public_token=public_token))
    except Exception as exc:
        _raise_plaid_error(exc)
    item_id = response["item_id"]
    access_token = response["access_token"]
    metadata = metadata or {}
    institution = metadata.get("institution") or {}

    existing = db.scalar(select(PlaidItem).where(PlaidItem.user_id == user.id, PlaidItem.plaid_item_id == item_id))
    plaid_item = existing or PlaidItem(user_id=user.id, plaid_item_id=item_id)
    plaid_item.access_token_encrypted = encrypt_access_token(access_token)
    plaid_item.institution_name = institution.get("name") or plaid_item.institution_name or "Connected Institution"
    plaid_item.institution_id = institution.get("institution_id") or plaid_item.institution_id
    plaid_item.status = "connected"
    plaid_item.error_code = None
    plaid_item.error_message = None
    plaid_item.reconnect_required_at = None
    plaid_item.disconnected_at = None
    plaid_item.consent_acknowledged_at = consent_acknowledged_at or plaid_item.consent_acknowledged_at or utc_now()
    db.add(plaid_item)
    db.commit()

    sync_plaid_item(db, plaid_item, purpose=purpose)
    return plaid_item


def sync_plaid_item(db: Session, plaid_item: PlaidItem, *, purpose: str = "account_sync") -> dict:
    _authorize_plaid_use(purpose, data_kind="transactions")
    if not plaid_item_is_syncable(plaid_item):
        raise PlaidRequestError("This Plaid connection is not syncable. Reconnect or remove the institution from Settings.")
    client = plaid_client()
    access_token = decrypt_access_token(plaid_item.access_token_encrypted)
    sync_accounts(db, plaid_item, client, access_token, purpose=purpose)

    cursor = plaid_item.sync_cursor
    added = []
    modified = []
    removed = []
    has_more = True

    while has_more:
        try:
            request_kwargs = {"access_token": access_token, "count": 500}
            if TransactionsSyncRequestOptions:
                request_kwargs["options"] = TransactionsSyncRequestOptions(
                    include_original_description=True,
                    include_personal_finance_category=True,
                )
            if cursor:
                request_kwargs["cursor"] = cursor
            response = client.transactions_sync(TransactionsSyncRequest(**request_kwargs))
        except Exception as exc:
            _raise_plaid_error(exc)
        _authorize_plaid_use(purpose, data_kind="transactions")
        added.extend(response["added"])
        modified.extend(response["modified"])
        removed.extend(response["removed"])
        has_more = response["has_more"]
        cursor = response["next_cursor"]

    for transaction in added:
        upsert_plaid_transaction(db, plaid_item, transaction, purpose=purpose)
    for transaction in modified:
        upsert_plaid_transaction(db, plaid_item, transaction, purpose=purpose)
    for removed_transaction in removed:
        plaid_transaction_id = removed_transaction.get("transaction_id")
        if plaid_transaction_id:
            doomed = db.scalars(
                select(Transaction).where(
                    Transaction.user_id == plaid_item.user_id,
                    Transaction.plaid_transaction_id == plaid_transaction_id,
                )
            ).all()
            doomed_ids = [transaction.id for transaction in doomed]
            if doomed_ids:
                for ignore_row in db.scalars(
                    select(SubscriptionTransactionIgnore).where(
                        SubscriptionTransactionIgnore.user_id == plaid_item.user_id,
                        SubscriptionTransactionIgnore.transaction_id.in_(doomed_ids),
                    )
                ).all():
                    db.delete(ignore_row)
            for transaction in doomed:
                db.delete(transaction)

    plaid_item.sync_cursor = cursor
    plaid_item.last_synced_at = datetime.now(UTC).replace(tzinfo=None)
    plaid_item.status = "connected"
    plaid_item.error_code = None
    plaid_item.error_message = None
    db.commit()
    merge_duplicate_transactions_for_user(db, plaid_item.user)
    return {"added": len(added), "modified": len(modified), "removed": len(removed)}


def _json_safe_plaid_value(value):
    if hasattr(value, "to_dict"):
        return _json_safe_plaid_value(value.to_dict())
    if isinstance(value, dict):
        return {str(key): _json_safe_plaid_value(nested_value) for key, nested_value in value.items() if nested_value is not None}
    if isinstance(value, list):
        return [_json_safe_plaid_value(item) for item in value if item is not None]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def plaid_transaction_metadata(plaid_transaction) -> dict:
    metadata = {}
    for field in [
        "original_description",
        "payment_channel",
        "location",
        "personal_finance_category",
        "payment_meta",
        "logo_url",
        "website",
        "authorized_date",
        "authorized_datetime",
        "datetime",
        "account_owner",
        "transaction_code",
    ]:
        value = plaid_transaction.get(field)
        if value is not None:
            metadata[field] = _json_safe_plaid_value(value)
    return metadata


def remove_plaid_item(plaid_item: PlaidItem, *, purpose: str = "user_settings") -> None:
    _authorize_plaid_use(purpose, data_kind="access_token")
    if not plaid_item.access_token_encrypted:
        return
    client = plaid_client()
    access_token = decrypt_access_token(plaid_item.access_token_encrypted)
    try:
        client.item_remove(ItemRemoveRequest(access_token=access_token))
    except Exception as exc:
        _raise_plaid_error(exc)


def plaid_item_is_syncable(plaid_item: PlaidItem) -> bool:
    return bool(
        plaid_item
        and plaid_item.status in SYNCABLE_PLAID_STATUSES
        and plaid_item.access_token_encrypted
        and not plaid_item.disconnected_at
    )


def mark_plaid_item_reconnect_required(
    db: Session,
    plaid_item: PlaidItem,
    *,
    error_code: str = "ITEM_LOGIN_REQUIRED",
    error_message: str | None = None,
) -> PlaidItem:
    plaid_item.status = "reconnect_required"
    plaid_item.error_code = error_code
    plaid_item.error_message = error_message or "This institution requires you to reconnect through Plaid before ClearPath can sync it again."
    plaid_item.reconnect_required_at = utc_now()
    db.add(plaid_item)
    db.commit()
    return plaid_item


def handle_plaid_webhook(db: Session, payload: dict) -> dict:
    webhook_type = (payload.get("webhook_type") or "").upper()
    webhook_code = (payload.get("webhook_code") or "").upper()
    plaid_item_id = payload.get("item_id")
    plaid_item = db.scalar(select(PlaidItem).where(PlaidItem.plaid_item_id == plaid_item_id)) if plaid_item_id else None
    event_record = _prepare_plaid_webhook_event(db, payload, plaid_item, webhook_type, webhook_code)
    strong_idempotency_key = plaid_webhook_idempotency_key_is_strong(payload)
    if strong_idempotency_key and event_record.status == "processed":
        return {
            "handled": False,
            "status": "skipped",
            "duplicate": True,
            "event_id": event_record.id,
            "item_id": event_record.plaid_item_id,
        }

    event_record.status = "processing"
    event_record.error_message = None
    event_record.processed_at = None
    idempotency_key = event_record.idempotency_key
    db.add(event_record)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        event_record = db.scalar(select(PlaidWebhookEvent).where(PlaidWebhookEvent.idempotency_key == idempotency_key))
        if not event_record:
            raise
        if strong_idempotency_key and event_record.status == "processed":
            return {
                "handled": False,
                "status": "skipped",
                "duplicate": True,
                "event_id": event_record.id,
                "item_id": event_record.plaid_item_id,
            }
        event_record.status = "processing"
        event_record.error_message = None
        event_record.processed_at = None
        db.add(event_record)
        db.commit()
    event_record_id = event_record.id

    try:
        result = _process_plaid_webhook_payload(db, payload, webhook_type, webhook_code, plaid_item)
    except (PlaidConfigurationError, PlaidRequestError) as exc:
        db.rollback()
        _mark_plaid_webhook_failed(db, event_record_id, exc)
        logger.warning(
            "Plaid transaction webhook sync failed. plaid_item_id=%s webhook_code=%s error=%s",
            plaid_item.id if plaid_item else None,
            webhook_code,
            exc,
        )
        return {
            "handled": False,
            "item_id": plaid_item.id if plaid_item else None,
            "status": "sync_failed",
            "event_id": event_record_id,
        }
    except Exception as exc:
        db.rollback()
        _mark_plaid_webhook_failed(db, event_record_id, exc)
        raise

    event_record.status = "processed" if result.get("handled") else "skipped"
    event_record.processed_at = utc_now()
    db.add(event_record)
    db.commit()
    result["event_id"] = event_record_id
    return result


def _process_plaid_webhook_payload(db: Session, payload: dict, webhook_type: str, webhook_code: str, plaid_item: PlaidItem | None) -> dict:
    plaid_item_id = payload.get("item_id")

    if webhook_type == "ITEM" and webhook_code in RECONNECT_REQUIRED_CODES:
        if not plaid_item:
            return {"handled": False, "status": "unknown_item"}
        plaid_item = mark_plaid_item_reconnect_required(db, plaid_item, error_code=webhook_code)
        return {"handled": True, "item_id": plaid_item.id, "status": plaid_item.status}

    if webhook_type != "TRANSACTIONS" or webhook_code not in TRANSACTION_UPDATE_WEBHOOK_CODES or not plaid_item_id:
        return {"handled": False, "status": "ignored"}

    if not plaid_item:
        return {"handled": False, "status": "unknown_item"}
    if not plaid_item_is_syncable(plaid_item):
        return {"handled": False, "item_id": plaid_item.id, "status": plaid_item.status}

    result = sync_plaid_item(db, plaid_item, purpose="account_sync")
    run_post_sync_hooks(db, plaid_item.user)
    return {
        "handled": True,
        "item_id": plaid_item.id,
        "status": "synced",
        "added": result["added"],
        "modified": result["modified"],
        "removed": result["removed"],
    }


def _prepare_plaid_webhook_event(
    db: Session,
    payload: dict,
    plaid_item: PlaidItem | None,
    webhook_type: str,
    webhook_code: str,
) -> PlaidWebhookEvent:
    idempotency_key = plaid_webhook_idempotency_key(payload)
    existing = db.scalar(select(PlaidWebhookEvent).where(PlaidWebhookEvent.idempotency_key == idempotency_key))
    if existing and existing.status == "processed" and plaid_webhook_idempotency_key_is_strong(payload):
        return existing
    event_record = existing or PlaidWebhookEvent(idempotency_key=idempotency_key)
    event_record.plaid_item_id = plaid_item.id if plaid_item else None
    event_record.webhook_type = webhook_type or "UNKNOWN"
    event_record.webhook_code = webhook_code or "UNKNOWN"
    return event_record


def _normalize_plaid_text(value) -> str:
    return " ".join(str(value or "").strip().lower().replace("_", " ").split())


def _plaid_balance_for_account(plaid_account: dict, balances: dict) -> float:
    account_type = _normalize_plaid_text(plaid_account.get("type"))
    account_subtype = _normalize_plaid_text(plaid_account.get("subtype"))
    is_depository_cash = account_type == "depository" or account_subtype in DEPOSITORY_BALANCE_TYPES
    available_balance = balances.get("available")
    current_balance = balances.get("current")
    if is_depository_cash and available_balance is not None:
        return float(available_balance)
    if current_balance is not None:
        return float(current_balance)
    if available_balance is not None:
        return float(available_balance)
    return 0.0


def refresh_plaid_account_balances(db: Session, user: User, *, purpose: str = "forecast") -> dict:
    _authorize_plaid_use(purpose, data_kind="balances")
    if not plaid_status().get("ready", False):
        return {"synced": 0, "errors": []}
    client = plaid_client()
    synced = 0
    errors = []
    plaid_items = db.scalars(select(PlaidItem).where(PlaidItem.user_id == user.id, PlaidItem.status == "connected")).all()
    for plaid_item in plaid_items:
        if not plaid_item_is_syncable(plaid_item):
            continue
        try:
            access_token = decrypt_access_token(plaid_item.access_token_encrypted)
            sync_accounts(db, plaid_item, client, access_token, purpose=purpose)
        except (PlaidConfigurationError, PlaidRequestError) as exc:
            db.rollback()
            errors.append(str(exc))
        else:
            synced += 1
    if synced:
        db.commit()
    return {"synced": synced, "errors": errors}


def plaid_webhook_idempotency_key(payload: dict) -> str:
    webhook_type = (payload.get("webhook_type") or "").upper()
    webhook_code = (payload.get("webhook_code") or "").upper()
    item_id = payload.get("item_id") or ""
    detail = {}
    for key in [
        "webhook_id",
        "cursor",
        "next_cursor",
        "new_transactions",
        "removed_transactions",
        "transactions_removed",
        "initial_update_complete",
        "historical_update_complete",
        "environment",
    ]:
        if key not in payload:
            continue
        value = payload.get(key)
        if isinstance(value, list):
            detail[key] = len(value)
        else:
            detail[key] = value
    detail_token = json.dumps(detail, sort_keys=True, default=str) if detail else "no-detail"
    raw_key = json.dumps(
        {
            "item_id": item_id,
            "webhook_type": webhook_type,
            "webhook_code": webhook_code,
            "detail": detail_token,
        },
        sort_keys=True,
    )
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def plaid_webhook_idempotency_key_is_strong(payload: dict) -> bool:
    for key in ("webhook_id", "cursor", "next_cursor"):
        value = payload.get(key)
        if value not in (None, "", [], {}):
            return True
    return False


def _mark_plaid_webhook_failed(db: Session, event_id: int, exc: Exception) -> None:
    failed_event = db.get(PlaidWebhookEvent, event_id)
    if failed_event:
        failed_event.status = "failed"
        failed_event.error_message = (str(exc) or "")[:1000]
        failed_event.processed_at = utc_now()
        db.add(failed_event)
        db.commit()


def cleanup_disconnected_plaid_data(db: Session, plaid_item: PlaidItem) -> None:
    accounts = db.scalars(select(Account).where(Account.user_id == plaid_item.user_id, Account.plaid_item_id == plaid_item.id)).all()
    account_ids = [account.id for account in accounts]

    if account_ids:
        for transaction in db.scalars(
            select(Transaction).where(Transaction.user_id == plaid_item.user_id, Transaction.account_id.in_(account_ids))
        ).all():
            transaction.plaid_transaction_id = None

    for account in accounts:
        account.is_manual = True
        account.plaid_account_id = None
        account.plaid_item_id = None
        account.mask = None
        account.cash_projection_role = "exclude"
        db.add(account)

    for ignored in db.scalars(
        select(PlaidAccountIgnore).where(PlaidAccountIgnore.user_id == plaid_item.user_id, PlaidAccountIgnore.plaid_item_id == plaid_item.id)
    ).all():
        db.delete(ignored)

    plaid_item.access_token_encrypted = ""
    plaid_item.sync_cursor = None
    plaid_item.institution_id = None
    plaid_item.error_code = None
    plaid_item.error_message = None
    plaid_item.reconnect_required_at = None
    plaid_item.disconnected_at = plaid_item.disconnected_at or utc_now()
    plaid_item.status = "disconnected"
    plaid_item.plaid_item_id = f"disconnected:{plaid_item.id}"
    db.add(plaid_item)


def disconnect_plaid_item(db: Session, plaid_item: PlaidItem, *, purpose: str = "user_settings") -> dict:
    _authorize_plaid_use(purpose, data_kind="access_token")
    already_disconnected = plaid_item.status == "disconnected" or bool(plaid_item.disconnected_at)
    if not already_disconnected:
        remove_plaid_item(plaid_item, purpose=purpose)
    cleanup_disconnected_plaid_data(db, plaid_item)
    db.commit()
    return {"disconnected": True, "already_disconnected": already_disconnected}


def sync_accounts(db: Session, plaid_item: PlaidItem, client, access_token: str, *, purpose: str = "account_sync") -> None:
    _authorize_plaid_use(purpose, data_kind="accounts")
    try:
        response = client.accounts_get(AccountsGetRequest(access_token=access_token) if AccountsGetRequest else {"access_token": access_token})
    except Exception as exc:
        _raise_plaid_error(exc)
    _authorize_plaid_use(purpose, data_kind="balances")
    for plaid_account in response["accounts"]:
        if db.scalar(
            select(PlaidAccountIgnore).where(
                PlaidAccountIgnore.user_id == plaid_item.user_id,
                PlaidAccountIgnore.plaid_account_id == plaid_account["account_id"],
            )
        ):
            continue
        account = db.scalar(
            select(Account).where(Account.user_id == plaid_item.user_id, Account.plaid_account_id == plaid_account["account_id"])
        )
        if not account:
            account = Account(user_id=plaid_item.user_id, plaid_account_id=plaid_account["account_id"])
        balances = plaid_account.get("balances") or {}
        account.name = plaid_account.get("name") or plaid_account.get("official_name") or "Plaid Account"
        account.account_type = str(plaid_account.get("subtype") or plaid_account.get("type") or "checking")
        account.institution = plaid_item.institution_name
        account.current_balance = _plaid_balance_for_account(plaid_account, balances)
        account.is_manual = False
        account.plaid_item_id = plaid_item.id
        account.mask = plaid_account.get("mask")
        account.updated_at = utc_now()
        db.add(account)
    db.flush()


def upsert_plaid_transaction(db: Session, plaid_item: PlaidItem, plaid_transaction, *, purpose: str = "account_sync") -> Transaction | None:
    _authorize_plaid_use(purpose, data_kind="transaction")
    plaid_transaction_id = plaid_transaction["transaction_id"]
    if db.scalar(
        select(PlaidAccountIgnore).where(
            PlaidAccountIgnore.user_id == plaid_item.user_id,
            PlaidAccountIgnore.plaid_account_id == plaid_transaction["account_id"],
        )
    ):
        existing = db.scalar(
            select(Transaction).where(Transaction.user_id == plaid_item.user_id, Transaction.plaid_transaction_id == plaid_transaction_id)
        )
        if existing:
            db.delete(existing)
            db.flush()
        return existing
    account = db.scalar(
        select(Account).where(Account.user_id == plaid_item.user_id, Account.plaid_account_id == plaid_transaction["account_id"])
    )
    description = plaid_transaction.get("merchant_name") or plaid_transaction.get("name") or "Plaid transaction"
    posted_date = _coerce_plaid_date(plaid_transaction.get("date"))
    amount = -float(plaid_transaction.get("amount") or 0)
    transaction_type = "income" if amount > 0 else "expense"
    import_hash = build_import_hash(posted_date, description, amount, account.name if account else plaid_item.institution_name or "Plaid")
    existing = db.scalar(
        select(Transaction).where(Transaction.user_id == plaid_item.user_id, Transaction.plaid_transaction_id == plaid_transaction_id)
    )
    if not existing:
        existing = db.scalars(
            select(Transaction)
            .where(
                Transaction.user_id == plaid_item.user_id,
                Transaction.import_hash == import_hash,
                Transaction.plaid_transaction_id.is_(None),
            )
            .order_by(Transaction.id.asc())
        ).first()
    transaction = existing or Transaction(user_id=plaid_item.user_id, plaid_transaction_id=plaid_transaction_id, import_hash=import_hash)
    transaction.plaid_transaction_id = plaid_transaction_id
    transaction.import_hash = import_hash
    previous_category_id = transaction.category_id
    transaction.account_id = account.id if account else None
    transaction.posted_date = posted_date
    transaction.description = description
    transaction.merchant = plaid_transaction.get("merchant_name") or description
    transaction.amount = amount
    transaction.transaction_type = transaction_type
    transaction.source_name = account.name if account else plaid_item.institution_name
    transaction.pending = bool(plaid_transaction.get("pending"))
    metadata = plaid_transaction_metadata(plaid_transaction)
    transaction.plaid_metadata = json.dumps(metadata, sort_keys=True) if metadata else None
    suggested_category = category_for_plaid_transaction(
        db,
        plaid_item.user,
        plaid_transaction,
        description,
        account_name=transaction.source_name,
        amount=amount,
        purpose=purpose,
    )
    if not previous_category_id or _is_other_category(db, previous_category_id):
        transaction.category_id = suggested_category.id if suggested_category else None
    db.add(transaction)
    return transaction


def _is_other_category(db: Session, category_id: int | None) -> bool:
    if not category_id:
        return True
    category = db.get(Category, category_id)
    return bool(category and category.name == "Other")


def _coerce_plaid_date(raw_date) -> date:
    if isinstance(raw_date, date):
        return raw_date
    return datetime.strptime(str(raw_date), "%Y-%m-%d").date()


def category_for_plaid_transaction(
    db: Session,
    user: User,
    plaid_transaction,
    description: str,
    account_name: str | None = None,
    amount: float | None = None,
    *,
    purpose: str = "account_sync",
) -> Category | None:
    _authorize_plaid_use(purpose, data_kind="personal_finance_category")
    personal_category = plaid_transaction.get("personal_finance_category") or {}
    primary = (personal_category.get("primary") or "").lower()
    detailed = (personal_category.get("detailed") or "").lower()
    grocery_haystack = normalize_text(
        " ".join(
            [
                description or "",
                plaid_transaction.get("merchant_name") or "",
                plaid_transaction.get("name") or "",
                account_name or "",
            ]
        )
    )
    grocery_merchant_terms = ("kroger", "walmart", "wal mart", "wm supercenter", "costco", "sam s club", "sams club", "aldi", "meijer")
    category_name = None
    if looks_like_credit_card_payment(description, plaid_transaction.get("merchant_name"), plaid_transaction.get("name"), account_name):
        category_name = CREDIT_CARD_PAYMENT_CATEGORY_NAME
    elif "income" in primary:
        category_name = "Income"
    elif "transfer" in primary:
        category_name = "Transfers"
    elif "groceries" in detailed or any(term in grocery_haystack for term in grocery_merchant_terms):
        category_name = "Groceries"
    elif "food_and_drink" in primary or "restaurant" in detailed:
        category_name = "Dining/Eating Out"
    elif "transportation" in primary or "gas" in detailed:
        category_name = "Fuel/Gasoline"
    elif "rent" in detailed or "mortgage" in detailed:
        category_name = "Mortgage/Rent"
    elif "medical" in primary:
        category_name = "Doctor/Dentist"
    elif "travel" in primary:
        category_name = "Vacation/Travel"
    elif "entertainment" in primary:
        category_name = "Movies/Theater/Concerts/Plays"
    elif "shops" in primary or "general_merchandise" in primary:
        category_name = "Personal Supplies"

    rule_category = apply_category_rules(db, user, description, account_name=account_name, amount=amount, category_name=category_name)
    if rule_category and rule_category.name != "Other":
        return rule_category

    if category_name:
        category = db.scalar(select(Category).where(Category.user_id == user.id, Category.name == category_name))
        if not category:
            category = db.scalar(
                select(Category).where(Category.user_id.is_(None), Category.name == category_name, Category.is_default.is_(True))
            )
        if not category:
            category = Category(
                user_id=user.id,
                name=category_name,
                kind="income" if category_name == "Income" else ("transfer" if category_name in {"Transfers", CREDIT_CARD_PAYMENT_CATEGORY_NAME} else "expense"),
                monthly_target=DEFAULT_CATEGORY_TARGETS.get(category_name, 0),
                is_default=False,
            )
            db.add(category)
            db.flush()
        if category:
            return category
    return rule_category


def maybe_refresh_live_bank_data(db: Session, user: User, *, min_interval_minutes: int | None = None) -> dict:
    settings = get_settings()
    if not settings.auto_refresh_plaid_on_page_load:
        return {"synced": 0, "errors": []}
    if not plaid_status().get("ready", False):
        return {"synced": 0, "errors": []}

    if min_interval_minutes is None:
        min_interval_minutes = settings.plaid_auto_refresh_min_interval_minutes

    now = datetime.now(UTC).replace(tzinfo=None)
    synced = 0
    errors = []
    plaid_items = db.scalars(select(PlaidItem).where(PlaidItem.user_id == user.id, PlaidItem.status == "connected")).all()
    for plaid_item in plaid_items:
        if plaid_item.last_synced_at and (now - plaid_item.last_synced_at).total_seconds() < min_interval_minutes * 60:
            continue
        try:
            sync_plaid_item(db, plaid_item, purpose="account_sync")
        except (PlaidConfigurationError, PlaidRequestError) as exc:
            errors.append(str(exc))
        else:
            synced += 1

    if synced:
        run_post_sync_hooks(db, user)
    return {"synced": synced, "errors": errors}
