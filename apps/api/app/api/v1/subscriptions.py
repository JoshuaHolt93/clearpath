from __future__ import annotations

import csv
import io
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.feature_access import feature_is_temporarily_hidden, feature_min_plan_label, user_has_feature
from app.dependencies import Principal, require_household_access
from app.models import Subscription, SubscriptionTransactionIgnore, Transaction, utc_now
from app.schemas.subscriptions import (
    SubscriptionCategoryBreakdownRow,
    SubscriptionCreateRequest,
    SubscriptionEvidenceItem,
    SubscriptionImportRequest,
    SubscriptionImportResponse,
    SubscriptionListResponse,
    SubscriptionLinkHelpRequest,
    SubscriptionLinkHelpResponse,
    SubscriptionOpportunity,
    SubscriptionResponse,
    SubscriptionScanResponse,
    SubscriptionSummary,
    SubscriptionUpdateRequest,
)
from app.services.planner_service import find_subscription_manage_links
from app.services.subscription_service import (
    KNOWN_SERVICES,
    SUBSCRIPTION_CATEGORY,
    SUBSCRIPTION_CYCLE_OPTIONS,
    SUBSCRIPTION_STATUSES,
    average_subscription_confidence,
    normalize_subscription_merchant,
    parsed_subscription_evidence,
    refresh_subscription_amounts_from_evidence,
    scan_and_sync_subscriptions,
    subscription_category_breakdown,
    subscription_evidence_map,
    subscription_opportunities,
    subscription_summary,
    upcoming_subscriptions,
)
from app.services.planning_service import app_today, sync_monthly_plan
from app.services.transaction_service import (
    build_import_hash,
    decode_csv_payload,
    ensure_category_option,
    is_onboarding_complete,
    parse_amount,
    parse_flexible_date,
)

router = APIRouter(tags=["subscriptions"])

editor_access = require_household_access("editor")
viewer_access = require_household_access("viewer")


def _require_subscription_feature(principal: Principal) -> None:
    # Flask order: ensure_onboarded() first, then the plan-tier feature gate.
    if not is_onboarding_complete(principal.user):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "onboarding_required", "message": "Complete onboarding before managing subscriptions."},
        )
    if not user_has_feature(principal.user, "subscriptions"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "feature_locked",
                "message": f"Subscription management requires ClearPath {feature_min_plan_label('subscriptions')} or higher.",
            },
        )


def _get_owned_subscription(db: Session, principal: Principal, subscription_id: int) -> Subscription:
    subscription = db.scalar(
        select(Subscription).where(Subscription.id == subscription_id, Subscription.user_id == principal.user.id)
    )
    if not subscription:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found.")
    return subscription


def _subscription_response(subscription: Subscription, evidence_rows: list[dict] | None = None) -> SubscriptionResponse:
    response = SubscriptionResponse.model_validate(subscription)
    if evidence_rows is None:
        evidence_rows = parsed_subscription_evidence(subscription)
    response.evidence = [SubscriptionEvidenceItem.model_validate(item) for item in evidence_rows]
    return response


def _list_response(db: Session, principal: Principal) -> SubscriptionListResponse:
    summary = subscription_summary(db, principal.user, purpose="subscriptions")
    subscriptions = summary["subscriptions"]
    evidence = subscription_evidence_map(subscriptions)
    transaction_count = db.scalar(
        select(Transaction.id).where(Transaction.user_id == principal.user.id, Transaction.amount < 0).limit(1)
    )
    negative_count = (
        len(db.scalars(select(Transaction.id).where(Transaction.user_id == principal.user.id, Transaction.amount < 0)).all())
        if transaction_count
        else 0
    )
    return SubscriptionListResponse(
        subscriptions=[_subscription_response(subscription, evidence.get(subscription.id, [])) for subscription in subscriptions],
        summary=SubscriptionSummary(
            active_count=summary["active_count"],
            review_count=summary["review_count"],
            action_count=summary["action_count"],
            manage_link_count=summary["manage_link_count"],
            monthly_total=summary["monthly_total"],
            annual_total=summary["annual_total"],
            potential_savings=summary["potential_savings"],
            average_confidence=average_subscription_confidence(subscriptions),
            transaction_count=negative_count,
        ),
        category_breakdown=[SubscriptionCategoryBreakdownRow(**row) for row in subscription_category_breakdown(subscriptions)],
        opportunities=[
            SubscriptionOpportunity(subscription_id=row["subscription"].id, reason=row["reason"])
            for row in subscription_opportunities(subscriptions)
        ],
        upcoming_subscription_ids=[subscription.id for subscription in upcoming_subscriptions(subscriptions)],
        statuses=SUBSCRIPTION_STATUSES,
        cycles=list(SUBSCRIPTION_CYCLE_OPTIONS),
    )


@router.get("/subscriptions", response_model=SubscriptionListResponse)
def list_subscriptions(
    principal: Annotated[Principal, Depends(viewer_access)],
    db: Annotated[Session, Depends(get_db)],
) -> SubscriptionListResponse:
    _require_subscription_feature(principal)
    return _list_response(db, principal)


@router.post("/subscriptions/scan", response_model=SubscriptionScanResponse)
def scan_subscriptions(
    principal: Annotated[Principal, Depends(editor_access)],
    db: Annotated[Session, Depends(get_db)],
) -> SubscriptionScanResponse:
    _require_subscription_feature(principal)
    synced = scan_and_sync_subscriptions(db, principal.user, purpose="subscriptions")
    sync_monthly_plan(db, principal.user, purpose="monthly_plan")
    return SubscriptionScanResponse(
        synced_count=len(synced),
        subscriptions=[_subscription_response(subscription) for subscription in synced],
    )


@router.post("/subscriptions", response_model=SubscriptionResponse, status_code=status.HTTP_201_CREATED)
def add_manual_subscription(
    payload: SubscriptionCreateRequest,
    principal: Annotated[Principal, Depends(editor_access)],
    db: Annotated[Session, Depends(get_db)],
) -> SubscriptionResponse:
    _require_subscription_feature(principal)
    name = (payload.name or "").strip()
    amount = parse_amount(payload.amount)
    cycle_days_by_name = {"Weekly": 7, "Biweekly": 14, "Monthly": 30, "Quarterly": 91, "Annual": 365}
    multiplier_by_name = {"Weekly": 52 / 12, "Biweekly": 26 / 12, "Monthly": 1, "Quarterly": 1 / 3, "Annual": 1 / 12}
    service = KNOWN_SERVICES.get(normalize_subscription_merchant(name), {})
    raw_next_charge = (payload.next_charge_date or "").strip()
    try:
        next_charge_date = parse_flexible_date(raw_next_charge) if raw_next_charge else None
    except ValueError:
        next_charge_date = None
    if not name or amount <= 0:
        raise HTTPException(status_code=422, detail="Subscription name and amount are required.")
    if payload.cycle not in cycle_days_by_name:
        raise HTTPException(status_code=422, detail="Choose a valid subscription cadence.")
    if raw_next_charge and not next_charge_date:
        raise HTTPException(status_code=422, detail="Enter a valid next charge date.")

    monthly_amount = round(amount * multiplier_by_name[payload.cycle], 2)
    subscription = Subscription(
        user_id=principal.user.id,
        merchant_key=normalize_subscription_merchant(name),
        name=service.get("name") or name,
        category=SUBSCRIPTION_CATEGORY,
        service_category=service.get("category") or "Manual",
        amount=amount,
        monthly_amount=monthly_amount,
        annual_amount=round(monthly_amount * 12, 2),
        cycle=payload.cycle,
        cycle_days=cycle_days_by_name[payload.cycle],
        confidence=1,
        status="active",
        cancel_url=service.get("cancel_url"),
        replaceable=service.get("replaceable", True),
        next_charge_date=next_charge_date,
        first_seen=next_charge_date,
        last_seen=next_charge_date,
        notes=(payload.notes or "").strip() or None,
        is_manual=True,
        cycle_is_manual=True,
    )
    db.add(subscription)
    db.commit()
    db.refresh(subscription)
    sync_monthly_plan(db, principal.user, purpose="monthly_plan")
    return _subscription_response(subscription)


@router.patch("/subscriptions/{subscription_id}", response_model=SubscriptionResponse)
def update_subscription(
    subscription_id: int,
    payload: SubscriptionUpdateRequest,
    principal: Annotated[Principal, Depends(editor_access)],
    db: Annotated[Session, Depends(get_db)],
) -> SubscriptionResponse:
    _require_subscription_feature(principal)
    subscription = _get_owned_subscription(db, principal, subscription_id)

    if payload.cycle is not None:
        cycle = SUBSCRIPTION_CYCLE_OPTIONS.get(payload.cycle.strip())
        if not cycle:
            raise HTTPException(status_code=422, detail="Choose a valid subscription cycle.")
        subscription.cycle = payload.cycle.strip()
        subscription.cycle_days = cycle["days"]
        subscription.monthly_amount = round(subscription.amount * cycle["monthly_multiplier"], 2)
        subscription.annual_amount = round(subscription.monthly_amount * 12, 2)
        subscription.cycle_is_manual = True
        if subscription.last_seen:
            subscription.next_charge_date = subscription.last_seen + timedelta(days=cycle["days"])

    if payload.cancel_url is not None:
        manage_url = payload.cancel_url.strip()
        if manage_url and not manage_url.lower().startswith(("https://", "http://")):
            raise HTTPException(status_code=422, detail="Enter a full website address that starts with http:// or https://.")
        subscription.cancel_url = manage_url or None

    if payload.status is not None:
        new_status = payload.status.strip()
        if new_status not in SUBSCRIPTION_STATUSES:
            raise HTTPException(status_code=422, detail="Choose a valid subscription status.")
        subscription.status = new_status
        if payload.notes is not None:
            subscription.notes = payload.notes.strip() or None
    elif payload.notes is not None:
        subscription.notes = payload.notes.strip() or None

    db.commit()
    db.refresh(subscription)
    sync_monthly_plan(db, principal.user, purpose="monthly_plan")
    return _subscription_response(subscription)


@router.post("/subscriptions/{subscription_id}/evidence/{transaction_id}/ignore", response_model=SubscriptionResponse)
def ignore_subscription_evidence(
    subscription_id: int,
    transaction_id: int,
    principal: Annotated[Principal, Depends(editor_access)],
    db: Annotated[Session, Depends(get_db)],
) -> SubscriptionResponse:
    _require_subscription_feature(principal)
    subscription = _get_owned_subscription(db, principal, subscription_id)
    transaction = db.scalar(
        select(Transaction).where(Transaction.id == transaction_id, Transaction.user_id == principal.user.id)
    )
    if not transaction:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found.")
    existing_ignore = db.scalar(
        select(SubscriptionTransactionIgnore).where(
            SubscriptionTransactionIgnore.user_id == principal.user.id,
            SubscriptionTransactionIgnore.transaction_id == transaction.id,
        )
    )
    if not existing_ignore:
        db.add(
            SubscriptionTransactionIgnore(
                user_id=principal.user.id,
                transaction_id=transaction.id,
                subscription_id=subscription.id,
                merchant_key=subscription.merchant_key,
                amount=abs(transaction.amount),
                description=transaction.description,
            )
        )

    evidence_items = [
        item
        for item in parsed_subscription_evidence(subscription)
        if str(item.get("id")) != str(transaction.id)
    ]
    refresh_subscription_amounts_from_evidence(subscription, evidence_items)
    db.commit()
    db.refresh(subscription)
    sync_monthly_plan(db, principal.user, purpose="monthly_plan")
    return _subscription_response(subscription)


@router.post(
    "/subscriptions/{subscription_id}/link-help",
    response_model=SubscriptionLinkHelpResponse,
)
def subscription_link_help(
    subscription_id: int,
    _payload: SubscriptionLinkHelpRequest,
    principal: Annotated[Principal, Depends(editor_access)],
    db: Annotated[Session, Depends(get_db)],
) -> SubscriptionLinkHelpResponse:
    _require_subscription_feature(principal)
    if not user_has_feature(principal.user, "ai_coach"):
        if feature_is_temporarily_hidden("ai_coach"):
            raise HTTPException(status_code=403, detail="AI link help is not available during the current ClearPath validation period.")
        raise HTTPException(status_code=403, detail="AI link help requires ClearPath Premier.")
    subscription = _get_owned_subscription(db, principal, subscription_id)
    return SubscriptionLinkHelpResponse.model_validate(
        find_subscription_manage_links(db, principal.user, subscription)
    )


@router.post("/subscription-imports", response_model=SubscriptionImportResponse)
def import_subscription_csv(
    payload: SubscriptionImportRequest,
    principal: Annotated[Principal, Depends(editor_access)],
    db: Annotated[Session, Depends(get_db)],
) -> SubscriptionImportResponse:
    _require_subscription_feature(principal)
    content = decode_csv_payload(payload.csv_text, payload.csv_base64)
    reader = csv.DictReader(io.StringIO(content))
    if not reader.fieldnames:
        raise HTTPException(status_code=422, detail="CSV must include headers.")

    headers = {header.lower().strip(): header for header in reader.fieldnames}

    def get_value(row, names):
        for name in names:
            header = headers.get(name)
            if header:
                return (row.get(header) or "").strip()
        return ""

    imported = 0
    for row in reader:
        raw_date = get_value(row, ["date", "transaction date", "posted date"])
        description = get_value(row, ["description", "name", "merchant"])
        raw_amount = get_value(row, ["amount", "debit", "charge"])
        account_name = get_value(row, ["account", "source"]) or "Subscription CSV"
        category_name = get_value(row, ["category"]) or "Consumer Subscriptions"
        if not raw_date or not description or not raw_amount:
            continue
        try:
            posted_date = parse_flexible_date(raw_date)
            amount = -abs(parse_amount(raw_amount))
        except (ValueError, TypeError):
            continue

        category = ensure_category_option(db, category_name, principal.user)
        db.flush()
        import_hash = build_import_hash(posted_date, description, amount, account_name)
        if db.scalar(select(Transaction.id).where(Transaction.user_id == principal.user.id, Transaction.import_hash == import_hash).limit(1)):
            continue
        db.add(
            Transaction(
                user_id=principal.user.id,
                category_id=category.id,
                posted_date=posted_date,
                description=description,
                merchant=description,
                amount=amount,
                transaction_type="expense",
                source_name=account_name,
                import_hash=import_hash,
            )
        )
        imported += 1

    db.commit()
    synced = scan_and_sync_subscriptions(db, principal.user, purpose="subscriptions")
    sync_monthly_plan(db, principal.user, purpose="monthly_plan")
    return SubscriptionImportResponse(imported=imported, synced_count=len(synced))


@router.get("/subscriptions/export.csv")
def export_subscriptions_csv(
    principal: Annotated[Principal, Depends(viewer_access)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    _require_subscription_feature(principal)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["name", "category", "amount", "cycle", "monthly", "annual", "nextDate", "status", "confidence", "manageUrl", "source"])
    for subscription in subscription_summary(db, principal.user, purpose="subscriptions")["subscriptions"]:
        writer.writerow(
            [
                subscription.name,
                subscription.service_category,
                subscription.amount,
                subscription.cycle,
                subscription.monthly_amount,
                subscription.annual_amount,
                subscription.next_charge_date.isoformat() if subscription.next_charge_date else "",
                subscription.status,
                "manual" if subscription.is_manual else round(subscription.confidence * 100),
                subscription.cancel_url or "",
                "manual" if subscription.is_manual else "detected",
            ]
        )
    filename = f"clearpath-subscriptions-{app_today().isoformat()}.csv"
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
