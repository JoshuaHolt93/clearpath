from __future__ import annotations

import hmac
import json
import logging
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.planning_constants import ACCOUNT_CLASSIFICATION_OPTIONS
from app.core.security import create_purpose_token, decode_purpose_token
from app.dependencies import Principal, require_household_access
from app.models import Account, PlaidAccountIgnore, PlaidItem, Transaction, utc_now
from app.schemas.plaid import (
    AccountCashProjectionRoleUpdateRequest,
    AccountRemoveResponse,
    AccountTypeUpdateRequest,
    AccountResponse,
    PlaidExchangePublicTokenRequest,
    PlaidIgnoredAccountResponse,
    PlaidItemDisconnectResponse,
    PlaidItemListResponse,
    PlaidItemResponse,
    PlaidItemSyncResponse,
    PlaidLinkEventRequest,
    PlaidLinkEventResponse,
    PlaidLinkTokenResponse,
    PlaidRefreshStaleRequest,
    PlaidRefreshSummaryResponse,
    PlaidStatusResponse,
)
from app.services import plaid_service
from app.services.plaid_service import (
    PlaidConfigurationError,
    PlaidRequestError,
    create_link_token,
    disconnect_plaid_item,
    exchange_public_token,
    handle_plaid_webhook,
    maybe_refresh_live_bank_data,
    plaid_status,
    run_post_sync_hooks,
    sync_plaid_item,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["plaid"])

editor_access = require_household_access("editor")
viewer_access = require_household_access("viewer")


def _get_owned_plaid_item(db: Session, principal: Principal, item_id: int) -> PlaidItem:
    plaid_item = db.scalar(select(PlaidItem).where(PlaidItem.id == item_id, PlaidItem.user_id == principal.user.id))
    if not plaid_item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plaid connection not found.")
    return plaid_item


def _get_owned_account(db: Session, principal: Principal, account_id: int) -> Account:
    account = db.scalar(select(Account).where(Account.id == account_id, Account.user_id == principal.user.id))
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found.")
    return account


def _accounts_for_plaid_item(db: Session, plaid_item: PlaidItem) -> list[Account]:
    accounts = sorted(
        db.scalars(select(Account).where(Account.user_id == plaid_item.user_id, Account.plaid_item_id == plaid_item.id)).all(),
        key=lambda account: (account.name or "").lower(),
    )
    if accounts:
        return accounts
    if not plaid_item.institution_name:
        return []
    return sorted(
        [
            account
            for account in db.scalars(
                select(Account).where(Account.user_id == plaid_item.user_id, Account.is_manual.is_(False))
            ).all()
            if account.institution == plaid_item.institution_name
        ],
        key=lambda account: (account.name or "").lower(),
    )


def _plaid_item_response(db: Session, plaid_item: PlaidItem) -> PlaidItemResponse:
    response = PlaidItemResponse.model_validate(plaid_item)
    response.accounts = [AccountResponse.model_validate(account) for account in _accounts_for_plaid_item(db, plaid_item)]
    return response


@router.get("/plaid/status", response_model=PlaidStatusResponse)
def get_plaid_status(principal: Annotated[Principal, Depends(viewer_access)]) -> PlaidStatusResponse:
    return PlaidStatusResponse(**plaid_status())


@router.post("/plaid/link-token", response_model=PlaidLinkTokenResponse)
def plaid_link_token(principal: Annotated[Principal, Depends(editor_access)]) -> PlaidLinkTokenResponse:
    try:
        link_token = create_link_token(principal.user, purpose="account_sync")
    except (PlaidConfigurationError, PlaidRequestError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    # Flask recorded consent in the server session at link-token time and read
    # it back at exchange. The stateless equivalent is a signed purpose token
    # carrying the consent timestamp, which the client returns on exchange.
    consent_token = create_purpose_token(
        purpose="plaid_consent",
        subject=str(principal.user.id),
        minutes=60,
        extra={"consent_acknowledged_at": utc_now().isoformat()},
    )
    return PlaidLinkTokenResponse(link_token=link_token, consent_token=consent_token)


@router.post("/plaid/exchange-public-token", response_model=PlaidItemResponse)
def plaid_exchange_public_token(
    payload: PlaidExchangePublicTokenRequest,
    principal: Annotated[Principal, Depends(editor_access)],
    db: Annotated[Session, Depends(get_db)],
) -> PlaidItemResponse:
    if not payload.public_token:
        raise HTTPException(status_code=400, detail="Missing Plaid public token.")
    consent_acknowledged_at = None
    if payload.consent_token:
        try:
            consent_payload = decode_purpose_token(payload.consent_token, purpose="plaid_consent")
            if str(consent_payload.get("sub")) == str(principal.user.id):
                consent_acknowledged_at = datetime.fromisoformat(consent_payload["consent_acknowledged_at"])
        except Exception:
            consent_acknowledged_at = utc_now()
    try:
        plaid_item = exchange_public_token(
            db,
            principal.user,
            payload.public_token,
            payload.metadata or {},
            purpose="account_sync",
            consent_acknowledged_at=consent_acknowledged_at,
        )
    except (PlaidConfigurationError, PlaidRequestError) as exc:
        logger.warning("Plaid public token exchange failed. user_id=%s error=%s", principal.user.id, exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _plaid_item_response(db, plaid_item)


@router.post("/plaid/link-events", response_model=PlaidLinkEventResponse)
def plaid_link_event(
    payload: PlaidLinkEventRequest,
    principal: Annotated[Principal, Depends(editor_access)],
) -> PlaidLinkEventResponse:
    event_name = str(payload.event_name or payload.event or "unknown")[:80]
    error = payload.error if isinstance(payload.error, dict) else {}
    metadata = payload.metadata if isinstance(payload.metadata, dict) else {}
    institution = metadata.get("institution") if isinstance(metadata.get("institution"), dict) else {}
    logger.info(
        "Plaid Link client event. user_id=%s event=%s error_type=%s error_code=%s request_id=%s link_session_id=%s institution_id=%s",
        principal.user.id,
        event_name,
        str(error.get("error_type") or "")[:80],
        str(error.get("error_code") or "")[:80],
        str(error.get("request_id") or metadata.get("request_id") or "")[:120],
        str(metadata.get("link_session_id") or "")[:120],
        str(institution.get("institution_id") or "")[:120],
    )
    return PlaidLinkEventResponse(ok=True)


@router.get("/plaid-items", response_model=PlaidItemListResponse)
def list_plaid_items(
    principal: Annotated[Principal, Depends(viewer_access)],
    db: Annotated[Session, Depends(get_db)],
) -> PlaidItemListResponse:
    items = db.scalars(
        select(PlaidItem).where(PlaidItem.user_id == principal.user.id).order_by(PlaidItem.id.asc())
    ).all()
    ignored = db.scalars(
        select(PlaidAccountIgnore).where(PlaidAccountIgnore.user_id == principal.user.id).order_by(PlaidAccountIgnore.id.asc())
    ).all()
    return PlaidItemListResponse(
        items=[_plaid_item_response(db, item) for item in items],
        ignored_accounts=[PlaidIgnoredAccountResponse.model_validate(row) for row in ignored],
    )


@router.post("/plaid-items/{item_id}/sync", response_model=PlaidItemSyncResponse)
def plaid_sync_item(
    item_id: int,
    principal: Annotated[Principal, Depends(editor_access)],
    db: Annotated[Session, Depends(get_db)],
) -> PlaidItemSyncResponse:
    plaid_item = _get_owned_plaid_item(db, principal, item_id)
    try:
        result = sync_plaid_item(db, plaid_item, purpose="account_sync")
    except (PlaidConfigurationError, PlaidRequestError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    run_post_sync_hooks(db, principal.user)
    return PlaidItemSyncResponse(**result)


@router.delete("/plaid-items/{item_id}", response_model=PlaidItemDisconnectResponse)
def plaid_disconnect_item_endpoint(
    item_id: int,
    principal: Annotated[Principal, Depends(editor_access)],
    db: Annotated[Session, Depends(get_db)],
) -> PlaidItemDisconnectResponse:
    plaid_item = _get_owned_plaid_item(db, principal, item_id)
    try:
        result = disconnect_plaid_item(db, plaid_item, purpose="user_settings")
    except (PlaidConfigurationError, PlaidRequestError) as exc:
        raise HTTPException(status_code=400, detail=f"Plaid could not disconnect this institution yet: {exc}") from exc
    # Flask disconnect refreshes the monthly plan only (no subscription rescan).
    from app.services.planning_service import sync_monthly_plan

    sync_monthly_plan(db, principal.user, purpose="monthly_plan")
    return PlaidItemDisconnectResponse(**result)


@router.post("/plaid-items/refresh-stale", response_model=PlaidRefreshSummaryResponse)
def plaid_refresh_stale(
    payload: PlaidRefreshStaleRequest,
    principal: Annotated[Principal, Depends(editor_access)],
    db: Annotated[Session, Depends(get_db)],
) -> PlaidRefreshSummaryResponse:
    result = maybe_refresh_live_bank_data(db, principal.user, min_interval_minutes=payload.min_interval_minutes)
    return PlaidRefreshSummaryResponse(**result)


@router.delete("/accounts/{account_id}", response_model=AccountRemoveResponse)
def remove_synced_account(
    account_id: int,
    principal: Annotated[Principal, Depends(editor_access)],
    db: Annotated[Session, Depends(get_db)],
) -> AccountRemoveResponse:
    account = _get_owned_account(db, principal, account_id)
    if account.is_manual or not account.plaid_account_id:
        raise HTTPException(status_code=422, detail="Only synced accounts can be removed from this section.")

    ignored = db.scalar(
        select(PlaidAccountIgnore).where(
            PlaidAccountIgnore.user_id == principal.user.id,
            PlaidAccountIgnore.plaid_account_id == account.plaid_account_id,
        )
    )
    if not ignored:
        ignored = PlaidAccountIgnore(
            user_id=principal.user.id,
            plaid_item_id=account.plaid_item_id,
            plaid_account_id=account.plaid_account_id,
        )
        db.add(ignored)
    ignored.account_name = account.name
    ignored.institution_name = account.institution
    for transaction in db.scalars(
        select(Transaction).where(Transaction.user_id == principal.user.id, Transaction.account_id == account.id)
    ).all():
        db.delete(transaction)
    db.delete(account)
    db.commit()
    # Flask removal refreshes the monthly plan only (no subscription rescan).
    from app.services.planning_service import sync_monthly_plan

    sync_monthly_plan(db, principal.user, purpose="monthly_plan")
    return AccountRemoveResponse(removed=True, ignored_account_id=ignored.id)


@router.patch("/accounts/{account_id}/account-type", response_model=AccountResponse)
def update_account_type(
    account_id: int,
    payload: AccountTypeUpdateRequest,
    principal: Annotated[Principal, Depends(editor_access)],
    db: Annotated[Session, Depends(get_db)],
) -> AccountResponse:
    from app.services.planning_service import sync_monthly_plan

    account = _get_owned_account(db, principal, account_id)
    if account.is_manual or not account.plaid_account_id:
        raise HTTPException(status_code=422, detail="Only synced accounts can be classified from this section.")
    account_type = (payload.account_type or "").strip().lower()
    allowed_types = {value for value, _label in ACCOUNT_CLASSIFICATION_OPTIONS}
    if account_type not in allowed_types:
        raise HTTPException(status_code=422, detail="Choose a supported account type.")
    account.account_type = account_type
    db.commit()
    sync_monthly_plan(db, principal.user, purpose="monthly_plan")
    db.refresh(account)
    return AccountResponse.model_validate(account)


@router.patch("/accounts/{account_id}/cash-projection-role", response_model=AccountResponse)
def update_account_cash_projection_role(
    account_id: int,
    payload: AccountCashProjectionRoleUpdateRequest,
    principal: Annotated[Principal, Depends(editor_access)],
    db: Annotated[Session, Depends(get_db)],
) -> AccountResponse:
    account = _get_owned_account(db, principal, account_id)
    if not _cash_projection_account_is_manageable(db, principal, account):
        raise HTTPException(status_code=422, detail="That account is not attached to an active bank connection.")
    account.cash_projection_role = payload.cash_projection_role
    db.commit()
    db.refresh(account)
    return AccountResponse.model_validate(account)


def _cash_projection_account_is_manageable(db: Session, principal: Principal, account: Account) -> bool:
    from app.services.planning_service import cash_projection_account_is_manageable

    return cash_projection_account_is_manageable(db, principal.user, account)


@router.post("/plaid-ignored-accounts/{ignore_id}/restore", response_model=PlaidIgnoredAccountResponse)
def plaid_restore_account(
    ignore_id: int,
    principal: Annotated[Principal, Depends(editor_access)],
    db: Annotated[Session, Depends(get_db)],
) -> PlaidIgnoredAccountResponse:
    ignored = db.scalar(
        select(PlaidAccountIgnore).where(PlaidAccountIgnore.id == ignore_id, PlaidAccountIgnore.user_id == principal.user.id)
    )
    if not ignored:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ignored account not found.")
    response = PlaidIgnoredAccountResponse.model_validate(ignored)
    db.delete(ignored)
    db.commit()
    return response


def _verify_plaid_webhook_request(request: Request) -> bool:
    # Exact port of Flask _verify_plaid_webhook_request: shared secret via
    # X-ClearPath-Webhook-Secret header, webhook_secret query param, or a bare
    # query string. TESTING fallback when no secret is configured. Stronger
    # provider signature verification is tracked as post-migration tech debt.
    settings = get_settings()
    expected_secret = settings.plaid_webhook_secret
    if not expected_secret:
        return settings.is_testing
    provided_secret = request.headers.get("X-ClearPath-Webhook-Secret") or request.query_params.get("webhook_secret") or ""
    raw_query = request.url.query or ""
    if not provided_secret and raw_query and "=" not in raw_query:
        provided_secret = raw_query
    return hmac.compare_digest(str(provided_secret), str(expected_secret))


@router.post("/webhooks/plaid")
async def plaid_webhook(request: Request, db: Annotated[Session, Depends(get_db)]) -> dict:
    if not _verify_plaid_webhook_request(request):
        raise HTTPException(status_code=401, detail="Invalid Plaid webhook signature.")
    raw_body = await request.body()
    try:
        payload = json.loads(raw_body) if raw_body else {}
    except json.JSONDecodeError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    result = handle_plaid_webhook(db, payload)
    return {"ok": True, "ignored": not result.get("handled", False), **result}
