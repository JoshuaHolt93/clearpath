from __future__ import annotations

import calendar
import re
from datetime import date, timedelta
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.feature_access import feature_min_plan_label, user_has_feature
from app.core.planning_constants import RECURRING_FREQUENCY_OPTIONS
from app.dependencies import Principal, require_household_access
from app.models import CashProjectionRecurringIgnore, RecurringForecastTemplate, User
from app.models.base import utc_now
from app.schemas.cash_projections import (
    CashProjectionAccountRowResponse,
    CashProjectionAutoRecurringRequest,
    CashProjectionCalendarFeedResponse,
    CashProjectionCalendarFeedUpdateRequest,
    CashProjectionPeriodResponse,
    CashProjectionRangeResponse,
    CashProjectionRefreshRequest,
    CashProjectionRefreshResultResponse,
    CashProjectionResponse,
    DetectedRecurringCashScheduleResponse,
    IgnoredRecurringCashScheduleResponse,
)
from app.services import plaid_service
from app.services.planning_service import (
    app_today,
    build_cash_projection_calendar_feed,
    build_cash_projection_period,
    build_cash_projection_range,
    cash_projection_account_rows,
    cash_projection_calendar_history_months,
    cash_projection_calendar_token_hash,
    clean_selected_weekdays,
    detected_recurring_cash_schedule,
    detected_recurring_transaction_schedules,
    generate_cash_projection_calendar_token,
    parse_month_input,
    recurring_monthly_week_pattern,
    split_projection_into_months,
    sync_monthly_plan,
)
from app.services.transaction_service import ensure_category_option, parse_flexible_date, require_onboarding_complete

router = APIRouter(tags=["cash-projections"])


def _require_cash_projection_access(user: User) -> None:
    require_onboarding_complete(user)
    if not user_has_feature(user, "cash_projection"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "feature_locked",
                "feature": "cash_projection",
                "required_plan": feature_min_plan_label("cash_projection"),
                "message": f"Cash Balance Projections require ClearPath {feature_min_plan_label('cash_projection')} or higher.",
            },
        )


def _add_calendar_months(target_date: date, months: int) -> date:
    month_index = target_date.month - 1 + months
    year = target_date.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, min(target_date.day, calendar.monthrange(year, month)[1]))


def _range_from_period(projection: dict, *, start_month: date, projections: list[dict] | None = None) -> dict:
    return {
        "start_month": start_month,
        "start_date": projection["start_date"],
        "end_date": projection["end_date"],
        "months": 0,
        "projections": projections or [projection],
        "days": projection["days"],
        "events": projection["events"],
        "start_balance": projection["start_balance"],
        "end_balance": projection["end_balance"],
        "balance_anchor": projection["balance_anchor"],
        "lowest_balance": projection["lowest_balance"],
        "highest_balance": projection["highest_balance"],
        "graph": projection["graph"],
    }


def _calendar_feed_response(request: Request, user: User) -> CashProjectionCalendarFeedResponse:
    token = user.cash_projection_calendar_token if user.cash_projection_calendar_enabled else None
    if not token or not user.cash_projection_calendar_token_hash:
        return CashProjectionCalendarFeedResponse(
            enabled=False,
            generated_at=None,
            history_months=cash_projection_calendar_history_months(user),
        )
    feed_url = str(request.url_for("cash_projection_calendar_feed", token=token))
    return CashProjectionCalendarFeedResponse(
        enabled=True,
        feed_url=feed_url,
        webcal_url=re.sub(r"^https?://", "webcal://", feed_url, count=1),
        google_url=f"https://calendar.google.com/calendar/render?cid={quote(feed_url, safe='')}",
        generated_at=user.cash_projection_calendar_generated_at,
        history_months=cash_projection_calendar_history_months(user),
    )


def _projection_response(
    db: Session,
    user: User,
    request: Request,
    *,
    month: str | None,
    horizon: str | None,
    view: str,
    start_date: str | None,
    end_date: str | None,
    refresh: dict | None = None,
) -> CashProjectionResponse:
    today = app_today()
    projection_min_date = _add_calendar_months(today, -6)
    projection_max_date = _add_calendar_months(today, 6)
    try:
        selected_month = parse_month_input(month) if (month or "").strip() else today
    except ValueError:
        selected_month = today
    if selected_month < projection_min_date.replace(day=1):
        selected_month = projection_min_date.replace(day=1)
    if selected_month > projection_max_date:
        selected_month = projection_max_date.replace(day=1)
    view_mode = (view or "calendar").strip().lower()
    if view_mode not in {"calendar", "list", "graph"}:
        view_mode = "calendar"
    saved_horizon = (user.cash_projection_default_horizon or "1m").strip().lower()
    if saved_horizon not in {"week", "1m", "3m", "6m"}:
        saved_horizon = "1m"
    selected_horizon = (horizon if horizon is not None else saved_horizon).strip().lower()
    if selected_horizon not in {"week", "1m", "3m", "6m", "custom"}:
        selected_horizon = saved_horizon
    custom_start = selected_month
    custom_end = selected_month
    if selected_horizon == "custom":
        try:
            custom_start = parse_flexible_date(start_date) if start_date else selected_month
        except ValueError:
            custom_start = selected_month
        custom_start = min(max(custom_start, projection_min_date), projection_max_date)
        try:
            custom_end = parse_flexible_date(end_date) if end_date else custom_start + timedelta(days=30)
        except ValueError:
            custom_end = custom_start + timedelta(days=30)
        custom_end = min(max(custom_end, projection_min_date), projection_max_date)
        custom_end = max(custom_end, custom_start)
        projection = build_cash_projection_period(db, user, custom_start, custom_end)
        projection_range = _range_from_period(
            projection,
            start_month=custom_start.replace(day=1),
            projections=split_projection_into_months(projection),
        )
    elif selected_horizon == "week":
        projection = build_cash_projection_period(db, user, selected_month, selected_month + timedelta(days=6))
        projection_range = _range_from_period(projection, start_month=selected_month.replace(day=1))
    else:
        projection_range = build_cash_projection_range(
            db,
            user,
            selected_month,
            {"1m": 1, "3m": 3, "6m": 6}[selected_horizon],
        )
        projection = projection_range["projections"][0]
    month_start = projection_range["start_month"]
    previous_month = date(month_start.year - 1, 12, 1) if month_start.month == 1 else date(month_start.year, month_start.month - 1, 1)
    next_month = date(month_start.year + 1, 1, 1) if month_start.month == 12 else date(month_start.year, month_start.month + 1, 1)
    account_rows = []
    for row in cash_projection_account_rows(db, user):
        account = row["account"]
        account_rows.append(
            CashProjectionAccountRowResponse(
                account_id=account.id,
                name=account.name,
                institution=account.institution,
                account_type=account.account_type,
                balance=account.current_balance or 0,
                mask=account.mask,
                role=row["role"],
                included=row["included"],
                status_label=row["status_label"],
                status_class=row["status_class"],
                status_detail=row["status_detail"],
            )
        )
    ignored_rows = db.scalars(
        select(CashProjectionRecurringIgnore)
        .where(CashProjectionRecurringIgnore.user_id == user.id)
        .order_by(CashProjectionRecurringIgnore.id.asc())
    ).all()
    return CashProjectionResponse(
        horizon=selected_horizon,
        view=view_mode,
        projection=CashProjectionPeriodResponse.model_validate(projection),
        projection_range=CashProjectionRangeResponse.model_validate(projection_range),
        previous_month=previous_month,
        next_month=next_month,
        custom_start=custom_start,
        custom_end=custom_end,
        custom_min_date=projection_min_date,
        custom_max_date=projection_max_date,
        projection_min_month=projection_min_date.strftime("%Y-%m"),
        projection_max_month=projection_max_date.strftime("%Y-%m"),
        account_rows=account_rows,
        detected_recurring=[
            DetectedRecurringCashScheduleResponse.model_validate(row)
            for row in detected_recurring_transaction_schedules(db, user, today)
        ],
        ignored_recurring=[
            IgnoredRecurringCashScheduleResponse.model_validate(
                {
                    "id": row.id,
                    "detection_key": row.detection_key,
                    "name": row.name,
                    "amount": row.amount,
                    "frequency": row.frequency,
                    "category_label": row.category_label,
                    "last_seen": row.last_seen,
                    "notes": row.notes,
                }
            )
            for row in ignored_rows
        ],
        calendar_feed=_calendar_feed_response(request, user),
        refresh=CashProjectionRefreshResultResponse.model_validate(refresh) if refresh is not None else None,
    )


@router.get("/cash-projections", response_model=CashProjectionResponse)
def get_cash_projection(
    request: Request,
    principal: Annotated[Principal, Depends(require_household_access("viewer"))],
    db: Annotated[Session, Depends(get_db)],
    month: Annotated[str | None, Query()] = None,
    horizon: Annotated[str | None, Query()] = None,
    view: Annotated[str, Query()] = "calendar",
    start_date: Annotated[str | None, Query()] = None,
    end_date: Annotated[str | None, Query()] = None,
) -> CashProjectionResponse:
    _require_cash_projection_access(principal.user)
    return _projection_response(
        db,
        principal.user,
        request,
        month=month,
        horizon=horizon,
        view=view,
        start_date=start_date,
        end_date=end_date,
    )


@router.post("/cash-projections/refresh", response_model=CashProjectionResponse)
def refresh_cash_projection(
    payload: CashProjectionRefreshRequest,
    request: Request,
    principal: Annotated[Principal, Depends(require_household_access("editor"))],
    db: Annotated[Session, Depends(get_db)],
) -> CashProjectionResponse:
    _require_cash_projection_access(principal.user)
    refresh_result = plaid_service.refresh_plaid_account_balances(db, principal.user, purpose="forecast")
    return _projection_response(
        db,
        principal.user,
        request,
        month=payload.month,
        horizon=payload.horizon,
        view=payload.view,
        start_date=payload.start_date,
        end_date=payload.end_date,
        refresh=refresh_result,
    )


@router.post("/cash-projections/auto-recurring/{detection_key}", response_model=CashProjectionResponse)
def update_auto_recurring_projection(
    detection_key: str,
    payload: CashProjectionAutoRecurringRequest,
    request: Request,
    principal: Annotated[Principal, Depends(require_household_access("editor"))],
    db: Annotated[Session, Depends(get_db)],
) -> CashProjectionResponse:
    user = principal.user
    _require_cash_projection_access(user)
    schedule = detected_recurring_cash_schedule(db, user, detection_key)
    if not schedule:
        raise HTTPException(status_code=404, detail="That suspected recurring charge is no longer active in projections.")
    existing_ignore = db.scalar(
        select(CashProjectionRecurringIgnore).where(
            CashProjectionRecurringIgnore.user_id == user.id,
            CashProjectionRecurringIgnore.detection_key == schedule["detection_key"],
        )
    )
    if payload.action == "save":
        name = (payload.name or schedule["name"] or "Recurring expense").strip()
        amount = float(payload.amount if payload.amount is not None else schedule["amount"])
        frequency = (payload.frequency or schedule["frequency"]).strip().lower()
        if frequency not in RECURRING_FREQUENCY_OPTIONS:
            frequency = schedule["frequency"]
        try:
            schedule_start = parse_flexible_date(payload.schedule_start_date) if payload.schedule_start_date else schedule["start_date"]
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Recurring charge needs a valid first expected date.") from exc
        try:
            second_date = parse_flexible_date(payload.second_date) if payload.second_date else None
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Enter a valid second date for twice-per-month recurring charges.") from exc
        selected_weekdays = clean_selected_weekdays(payload.recurring_days_of_week)
        monthly_week_numbers, monthly_weekday = recurring_monthly_week_pattern(
            payload.recurring_monthly_week_numbers,
            payload.recurring_monthly_weekday,
        )
        if frequency in {"weekly", "biweekly"} and not selected_weekdays:
            selected_weekdays = [str(schedule_start.weekday())]
        if not name or amount <= 0:
            raise HTTPException(status_code=422, detail="Recurring charge needs a name and positive amount.")
        template = RecurringForecastTemplate(
            user_id=user.id,
            name=name[:160],
            amount=amount,
            item_type="expense",
            frequency=frequency,
            start_date=schedule_start,
            second_date=second_date,
            days_of_week=",".join(selected_weekdays) if selected_weekdays else None,
            second_day_of_month=second_date.day if second_date else schedule.get("second_day_of_month"),
            monthly_week_numbers=monthly_week_numbers,
            monthly_weekday=monthly_weekday,
            category_label=(payload.category_label or "").strip() or schedule.get("category_label"),
            notes=(payload.notes or f"Adjusted from auto-detected recurring charge last seen {schedule['last_seen'].isoformat()}.").strip(),
        )
        ensure_category_option(db, template.category_label, user)
        db.add(template)
        if not existing_ignore:
            db.add(
                CashProjectionRecurringIgnore(
                    user_id=user.id,
                    detection_key=schedule["detection_key"],
                    name=schedule["name"],
                    amount=schedule["amount"],
                    frequency=schedule["frequency"],
                    category_label=schedule.get("category_label"),
                    last_seen=schedule.get("last_seen"),
                    notes="Converted to a user-managed recurring forecast template.",
                )
            )
        db.commit()
        sync_monthly_plan(db, user)
    elif not existing_ignore:
        db.add(
            CashProjectionRecurringIgnore(
                user_id=user.id,
                detection_key=schedule["detection_key"],
                name=schedule["name"],
                amount=schedule["amount"],
                frequency=schedule["frequency"],
                category_label=schedule.get("category_label"),
                last_seen=schedule.get("last_seen"),
                notes="Ignored from Cash Balance Projections by the user.",
            )
        )
        db.commit()
    return _projection_response(
        db,
        user,
        request,
        month=payload.month,
        horizon=payload.horizon,
        view=payload.view,
        start_date=payload.start_date,
        end_date=payload.end_date,
    )


@router.patch("/cash-projections/calendar-feed", response_model=CashProjectionCalendarFeedResponse)
def update_cash_projection_calendar_feed(
    payload: CashProjectionCalendarFeedUpdateRequest,
    request: Request,
    principal: Annotated[Principal, Depends(require_household_access("editor"))],
    db: Annotated[Session, Depends(get_db)],
) -> CashProjectionCalendarFeedResponse:
    user = principal.user
    _require_cash_projection_access(user)
    if payload.action == "disable":
        user.cash_projection_calendar_token = None
        user.cash_projection_calendar_token_hash = None
        user.cash_projection_calendar_enabled = False
        user.cash_projection_calendar_generated_at = None
    else:
        for _ in range(5):
            token = generate_cash_projection_calendar_token()
            token_hash = cash_projection_calendar_token_hash(token)
            existing = db.scalar(select(User).where(User.cash_projection_calendar_token_hash == token_hash))
            if not existing or existing.id == user.id:
                user.cash_projection_calendar_token = token
                user.cash_projection_calendar_token_hash = token_hash
                user.cash_projection_calendar_enabled = True
                user.cash_projection_calendar_generated_at = utc_now()
                break
        else:
            raise HTTPException(status_code=500, detail="Could not generate a unique calendar feed token.")
    db.commit()
    db.refresh(user)
    return _calendar_feed_response(request, user)


@router.get("/cash-projections/calendar/{token}.ics", name="cash_projection_calendar_feed")
def cash_projection_calendar_feed(
    token: str,
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    cleaned_token = (token or "").strip()
    if not cleaned_token:
        raise HTTPException(status_code=404, detail="Calendar feed not found.")
    user = db.scalar(
        select(User).where(
            User.cash_projection_calendar_token_hash == cash_projection_calendar_token_hash(cleaned_token),
            User.cash_projection_calendar_enabled.is_(True),
        )
    )
    if not user or not user_has_feature(user, "cash_projection"):
        raise HTTPException(status_code=404, detail="Calendar feed not found.")
    plaid_service.refresh_plaid_account_balances(db, user, purpose="forecast")
    feed = build_cash_projection_calendar_feed(db, user)
    return Response(
        content=feed,
        media_type="text/calendar; charset=utf-8",
        headers={
            "Content-Disposition": 'inline; filename="clearpath-cash-balance-projections.ics"',
            "Cache-Control": "private, max-age=300",
        },
    )
