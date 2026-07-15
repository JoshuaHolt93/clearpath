from __future__ import annotations

import calendar
import hashlib
import json
import math
import os
import re
import secrets
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.config import get_settings
from app.core.plaid_policy import assert_plaid_data_purpose
from app.core.planning_constants import (
    ADDITIONAL_MEDICARE_RATE,
    ADDITIONAL_MEDICARE_THRESHOLDS,
    ANALYTICS_RANGE_OPTIONS,
    BUDGET_CATEGORY_TRANSACTION_HINTS,
    CASH_ACCOUNT_TYPES,
    DEFAULT_APP_TIMEZONE,
    DEFAULT_CATEGORY_TARGETS,
    FEDERAL_TAX_BRACKETS_2026,
    FIXED_EXPENSE_CATEGORY_NAMES,
    MEDICARE_RATE_2026,
    MONTHLY_WEEK_OPTIONS,
    RECURRING_FREQUENCY_OPTIONS,
    SOCIAL_SECURITY_RATE_2026,
    SOCIAL_SECURITY_WAGE_BASE_2026,
    STANDARD_DEDUCTIONS_2026,
    STARTER_CATEGORY_GROUPS,
    STATE_TAX_RULES_2026,
    TAX_FILING_STATUS_OPTIONS,
    WEEKDAY_OPTIONS,
)
from app.models import (
    Category,
    CashProjectionRecurringIgnore,
    FixedExpenseItem,
    ForecastItem,
    Goal,
    LoanPlan,
    MonthlyBudgetCategorySnapshot,
    MonthlyBudgetSnapshot,
    MonthlyPlan,
    OnboardingProfile,
    PlaidItem,
    RecurringForecastTemplate,
    Transaction,
    TransactionSplit,
    User,
    VariableExpenseItem,
)
from app.core.planning_constants import LIABILITY_ACCOUNT_LABEL_KEYWORDS, LIABILITY_ACCOUNT_TYPES
from app.models import Account
from app.services import plaid_service
from app.services.transaction_service import (
    CREDIT_CARD_PAYMENT_CATEGORY_NAME,
    _transaction_description_match_score,
    categories_for_user,
    ensure_category_option,
    looks_like_credit_card_payment,
    normalize_text,
    transaction_duplicate_key,
)

# Faithful port of the planning foundations from Flask services.py at 9b5dff0:
# timezone/date helpers, income normalization, retirement and loan-extra
# contributions, savings targets, and the 2026 tax estimation engine. The
# worksheet occurrence engine, monthly plan sync, snapshots, and API services
# build on these foundations.


def app_timezone() -> ZoneInfo:
    timezone_name = (
        get_settings().app_timezone
        or os.getenv("APP_TIMEZONE")
        or os.getenv("CLEARPATH_TIMEZONE")
        or DEFAULT_APP_TIMEZONE
    )
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        return ZoneInfo(DEFAULT_APP_TIMEZONE)


def app_today(now: datetime | None = None) -> date:
    if now is None:
        return datetime.now(app_timezone()).date()
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    return now.astimezone(app_timezone()).date()


def month_bounds(target_date: date | None = None) -> tuple[date, date]:
    target_date = target_date or app_today()
    start = target_date.replace(day=1)
    end = target_date.replace(day=calendar.monthrange(target_date.year, target_date.month)[1])
    return start, end


def current_month_name(target_date: date | None = None) -> str:
    target_date = target_date or app_today()
    return target_date.strftime("%B %Y")


def add_months(target_date: date, months: int) -> date:
    month_index = target_date.month - 1 + months
    year = target_date.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, 1)


def payments_per_year(cadence: str | None) -> float:
    cadence = cadence or "monthly"
    if cadence == "annual":
        return 1
    if cadence == "semimonthly":
        return 24
    if cadence == "biweekly":
        return 26
    if cadence == "weekly":
        return 52
    return 12


def monthly_amount_for_frequency(amount: float, frequency: str | None) -> float:
    frequency = frequency or "monthly"
    if frequency == "annual":
        return amount / 12
    if frequency == "quarterly":
        return amount * 4 / 12
    if frequency == "semimonthly":
        return amount * 24 / 12
    if frequency == "biweekly":
        return amount * 26 / 12
    if frequency == "weekly":
        return amount * 52 / 12
    return amount


def weekday_values(days_of_week: str | None) -> list[int]:
    values = []
    for raw_value in (days_of_week or "").split(","):
        try:
            value = int(raw_value)
        except ValueError:
            continue
        if value in WEEKDAY_OPTIONS and value not in values:
            values.append(value)
    return sorted(values)


def monthly_week_values(monthly_week_numbers: str | None) -> list[int]:
    values = []
    for raw_value in (monthly_week_numbers or "").split(","):
        try:
            value = int(raw_value)
        except ValueError:
            continue
        if value in MONTHLY_WEEK_OPTIONS and value not in values:
            values.append(value)
    return sorted(values)


def monthly_amount_for_fixed_item(item: FixedExpenseItem) -> float:
    weekday_multiplier = len(weekday_values(item.days_of_week)) if item.frequency in {"weekly", "biweekly"} else 0
    multiplier = weekday_multiplier or 1
    return monthly_amount_for_frequency(item.amount, item.frequency) * multiplier


def monthly_amount_for_variable_item(item: VariableExpenseItem) -> float:
    weekday_multiplier = len(weekday_values(item.days_of_week)) if item.use_specific_date and item.frequency != "monthly" else 0
    multiplier = weekday_multiplier or 1
    return monthly_amount_for_frequency(item.amount, item.frequency) * multiplier


def _period_delta_days(cadence: str | None) -> int:
    cadence = cadence or "monthly"
    if cadence == "weekly":
        return 7
    if cadence == "biweekly":
        return 14
    if cadence == "semimonthly":
        return 15
    if cadence == "annual":
        return 365
    return 30


def monthly_income_from_profile(profile: OnboardingProfile | None) -> float:
    if not profile:
        return 0.0
    if not profile.income_amount and profile.monthly_income:
        return profile.monthly_income
    amount = profile.income_amount or 0
    income_type = getattr(profile, "income_type", None) or ("hourly" if profile.income_frequency == "hourly" else "salary")
    if income_type == "hourly":
        base_income = amount * (profile.hourly_hours_per_week or 40) * 52 / 12
    elif income_type == "bonus":
        base_income = monthly_amount_for_frequency(amount, profile.paycheck_cadence or profile.income_frequency or "monthly")
    else:
        base_income = annual_salary_from_profile(profile) / 12
    return base_income + additional_monthly_income_from_profile(profile)


def annual_salary_from_profile(profile: OnboardingProfile | None) -> float:
    if not profile:
        return 0.0
    amount = profile.income_amount or 0
    stored_monthly_income = profile.monthly_income or 0
    cadence = profile.paycheck_cadence or profile.income_frequency or "monthly"
    legacy_monthly_income = monthly_amount_for_frequency(amount, cadence)
    looks_like_legacy_paycheck_amount = (
        amount > 0
        and stored_monthly_income > 0
        and amount < stored_monthly_income * 6
        and abs(stored_monthly_income - legacy_monthly_income) <= max(10, stored_monthly_income * 0.05)
    )
    if looks_like_legacy_paycheck_amount:
        return stored_monthly_income * 12
    return amount


def additional_monthly_income_from_profile(profile: OnboardingProfile | None) -> float:
    if not profile:
        return 0.0
    return monthly_amount_for_frequency(
        getattr(profile, "additional_income_amount", 0) or 0,
        getattr(profile, "additional_income_frequency", "annual") or "annual",
    )


def retirement_monthly_contribution(profile: OnboardingProfile | None) -> float:
    if not profile or not profile.retirement_enabled:
        return 0.0
    employer_contribution = max(profile.retirement_monthly_contribution or 0, 0)
    personal_contribution = max(getattr(profile, "retirement_personal_monthly_contribution", 0) or 0, 0)
    return employer_contribution + personal_contribution


def retirement_cash_flow_contribution(profile: OnboardingProfile | None) -> float:
    if not profile or not profile.retirement_enabled:
        return 0.0
    employer_contribution = max(profile.retirement_monthly_contribution or 0, 0)
    personal_contribution = max(getattr(profile, "retirement_personal_monthly_contribution", 0) or 0, 0)
    if profile.retirement_employer_withheld and (profile.income_basis or "take_home") != "gross":
        employer_contribution = 0.0
    return employer_contribution + personal_contribution


def retirement_taxable_income_adjustment(profile: OnboardingProfile | None) -> float:
    if not profile or not profile.retirement_enabled or not profile.retirement_has_employer_plan:
        return 0.0
    if not profile.retirement_employer_withheld:
        return 0.0
    return max(profile.retirement_monthly_contribution or 0, 0) * 12


def selected_extra_payment_for_loan_plan(plan: LoanPlan | None) -> float:
    if not plan:
        return 0.0
    if plan.selected_scenario == "extra_one":
        return plan.extra_payment_one or 0.0
    if plan.selected_scenario == "extra_two":
        return plan.extra_payment_two or 0.0
    return 0.0


def scheduled_payment_for_term(principal: float, annual_rate: float, term_months: int) -> float:
    principal = max(principal or 0, 0)
    term_months = max(int(term_months or 0), 1)
    monthly_rate = max(annual_rate or 0, 0) / 100 / 12
    if principal <= 0:
        return 0.0
    if monthly_rate <= 0:
        return principal / term_months
    factor = (1 + monthly_rate) ** term_months
    return principal * monthly_rate * factor / (factor - 1)


def amortization_summary(
    principal: float,
    annual_rate: float,
    payment: float,
    extra_payment: float = 0.0,
    max_months: int = 360,
) -> dict:
    principal = max(principal or 0, 0)
    monthly_rate = max(annual_rate or 0, 0) / 100 / 12
    baseline_payment = scheduled_payment_for_term(principal, annual_rate, max_months) if max_months else (payment or 0)
    monthly_payment = max(baseline_payment + (extra_payment or 0), 0)
    if principal <= 0 or monthly_payment <= 0:
        return {"months": 0, "years": 0, "interest_paid": 0.0, "payoff_possible": principal <= 0}
    if monthly_rate and monthly_payment <= principal * monthly_rate:
        return {"months": max_months, "years": max_months / 12, "interest_paid": 0.0, "payoff_possible": False}

    balance = principal
    interest_paid = 0.0
    months = 0
    limit = max(max_months, 1) + 600
    while balance > 0.01 and months < limit:
        interest = balance * monthly_rate
        principal_paid = min(monthly_payment - interest, balance)
        if principal_paid <= 0:
            return {"months": months, "years": months / 12, "interest_paid": interest_paid, "payoff_possible": False}
        interest_paid += interest
        balance -= principal_paid
        months += 1
    return {"months": months, "years": months / 12, "interest_paid": interest_paid, "payoff_possible": balance <= 0.01}


def amortization_schedule(
    principal: float,
    annual_rate: float,
    payment: float,
    extra_payment: float = 0.0,
    max_months: int = 360,
    start_month: date | None = None,
) -> list[dict]:
    principal = max(principal or 0, 0)
    monthly_rate = max(annual_rate or 0, 0) / 100 / 12
    # Flask intentionally derives the baseline from the term whenever one is
    # present, even when regular_payment differs.
    baseline_payment = scheduled_payment_for_term(principal, annual_rate, max_months) if max_months else (payment or 0)
    monthly_payment = max(baseline_payment + (extra_payment or 0), 0)
    if principal <= 0 or monthly_payment <= 0:
        return []

    balance = principal
    rows = []
    start_month = (start_month or app_today()).replace(day=1)
    limit = max(max_months, 1) + 600
    for month_number in range(1, limit + 1):
        payment_date = add_months(start_month, month_number - 1)
        interest = balance * monthly_rate
        principal_paid = min(monthly_payment - interest, balance)
        if principal_paid <= 0:
            break
        ending_balance = max(balance - principal_paid, 0)
        rows.append(
            {
                "month": month_number,
                "payment_date": payment_date,
                "beginning_balance": balance,
                "payment": principal_paid + interest,
                "principal": principal_paid,
                "interest": interest,
                "ending_balance": ending_balance,
            }
        )
        balance = ending_balance
        if balance <= 0.01:
            break
    return rows


def loan_plan_scenarios(plan: LoanPlan) -> list[dict]:
    scenarios = [
        ("base", "Current Payment", 0.0),
        ("extra_one", "Extra Payment Scenario 1", plan.extra_payment_one or 0.0),
        ("extra_two", "Extra Payment Scenario 2", plan.extra_payment_two or 0.0),
    ]
    rows = []
    for key, label, extra in scenarios:
        result = amortization_summary(
            plan.principal_balance or 0,
            plan.annual_interest_rate or 0,
            plan.regular_payment or 0,
            extra,
            plan.term_months or 360,
        )
        rows.append({"key": key, "label": label, "extra_payment": extra, **result})
    return rows


def selected_loan_extra_payment_total(db: Session, user: User) -> float:
    total = 0.0
    for plan in db.scalars(select(LoanPlan).where(LoanPlan.user_id == user.id)).all():
        if plan.selected_scenario == "extra_one":
            total += plan.extra_payment_one or 0
        elif plan.selected_scenario == "extra_two":
            total += plan.extra_payment_two or 0
    return total


def savings_goal_monthly_contribution(db: Session, user: User) -> float:
    return sum(
        max(goal.monthly_contribution or 0, 0)
        for goal in db.scalars(select(Goal).where(Goal.user_id == user.id, Goal.goal_type == "savings")).all()
    )


def planned_savings_contribution_for_user(db: Session, user: User, profile: OnboardingProfile | None = None) -> float:
    profile = profile or user.profile or OnboardingProfile()
    profile_target = max(profile.planned_savings_contribution or 0, 0)
    goal_target = savings_goal_monthly_contribution(db, user)
    return max(profile_target, goal_target)


def variable_expense_plan_total(db: Session, user: User) -> float:
    items = db.scalars(select(VariableExpenseItem).where(VariableExpenseItem.user_id == user.id)).all()
    if items:
        return sum(monthly_amount_for_variable_item(item) for item in items)
    return user.profile.variable_expenses if user.profile else 0.0


def _month_range(month_start: date) -> tuple[date, date]:
    return month_start, month_start.replace(day=calendar.monthrange(month_start.year, month_start.month)[1])


def _append_generated_entry(entries: list[dict], when: date, description: str, amount: float, item_type: str, source: str, category_label: str | None = None, notes: str | None = None, source_id: int | str | None = None):
    entries.append(
        {
            "date": when,
            "description": description,
            "amount": amount,
            "item_type": item_type,
            "source": source,
            "category_label": category_label,
            "notes": notes,
            "source_id": source_id,
        }
    )


def _occurrence_day(start_date: date | None, fallback_day: int | None) -> int:
    if fallback_day and 1 <= fallback_day <= 31:
        return fallback_day
    if start_date:
        return start_date.day
    return 1


def _coerce_month_day(month_start: date, day_value: int) -> date:
    month_end_day = calendar.monthrange(month_start.year, month_start.month)[1]
    return month_start.replace(day=min(max(day_value, 1), month_end_day))


def _monthly_weekday_occurrence(month_start: date, weekday: int, week_number: int) -> date | None:
    month_start, month_end = _month_range(month_start)
    if weekday not in WEEKDAY_OPTIONS or week_number not in MONTHLY_WEEK_OPTIONS:
        return None
    if week_number == 5:
        current = month_end
        while current.weekday() != weekday:
            current -= timedelta(days=1)
        return current
    first = month_start
    while first.weekday() != weekday:
        first += timedelta(days=1)
    occurrence = first + timedelta(days=7 * (week_number - 1))
    return occurrence if occurrence <= month_end else None


def _occurrences_for_month(
    start_date: date,
    frequency: str,
    month_start: date,
    *,
    second_day_of_month: int | None = None,
    preferred_day: int | None = None,
    days_of_week: str | None = None,
    monthly_week_numbers: str | None = None,
    monthly_weekday: int | None = None,
) -> list[date]:
    month_start, month_end = _month_range(month_start)
    if month_end < start_date:
        return []

    primary_day = _occurrence_day(start_date, preferred_day)
    selected_weekdays = weekday_values(days_of_week)
    selected_monthly_weeks = monthly_week_values(monthly_week_numbers)
    occurrences: list[date] = []

    if frequency in {"monthly", "semimonthly"} and selected_monthly_weeks and monthly_weekday in WEEKDAY_OPTIONS:
        selected_weeks = selected_monthly_weeks[:1] if frequency == "monthly" else selected_monthly_weeks
        for week_number in selected_weeks:
            current = _monthly_weekday_occurrence(month_start, int(monthly_weekday), week_number)
            if current and current >= start_date:
                occurrences.append(current)
        return sorted(set(occurrences))

    if frequency == "weekly" and selected_weekdays:
        current = month_start
        while current <= month_end:
            if current >= start_date and current.weekday() in selected_weekdays:
                occurrences.append(current)
            current += timedelta(days=1)
        return occurrences

    if frequency == "weekly":
        current = start_date
        while current < month_start:
            current += timedelta(days=7)
        while current <= month_end:
            occurrences.append(current)
            current += timedelta(days=7)
        return occurrences

    if frequency == "biweekly" and selected_weekdays:
        anchor_week_start = start_date - timedelta(days=start_date.weekday())
        current = month_start
        while current <= month_end:
            current_week_start = current - timedelta(days=current.weekday())
            weeks_since_anchor = (current_week_start - anchor_week_start).days // 7
            if (
                current >= start_date
                and weeks_since_anchor >= 0
                and weeks_since_anchor % 2 == 0
                and current.weekday() in selected_weekdays
            ):
                occurrences.append(current)
            current += timedelta(days=1)
        return occurrences

    if frequency == "biweekly":
        current = start_date
        while current < month_start:
            current += timedelta(days=14)
        while current <= month_end:
            occurrences.append(current)
            current += timedelta(days=14)
        return occurrences

    if frequency == "monthly":
        current = _coerce_month_day(month_start, primary_day)
        return [current] if current >= start_date else []

    if frequency == "semimonthly":
        candidate_days = {primary_day}
        if second_day_of_month and 1 <= second_day_of_month <= 31:
            candidate_days.add(second_day_of_month)
        else:
            candidate_days.add(min(primary_day + 14, 28))
        for day_value in sorted(candidate_days):
            current = _coerce_month_day(month_start, day_value)
            if current >= start_date:
                occurrences.append(current)
        return occurrences

    if frequency == "quarterly":
        month_diff = (month_start.year - start_date.year) * 12 + (month_start.month - start_date.month)
        if month_diff >= 0 and month_diff % 3 == 0:
            current = _coerce_month_day(month_start, primary_day)
            return [current] if current >= start_date else []
        return []

    if frequency == "annual":
        if month_start.month == start_date.month and month_start.year >= start_date.year:
            current = _coerce_month_day(month_start, primary_day)
            return [current] if current >= start_date else []
        return []

    current = _coerce_month_day(month_start, primary_day)
    return [current] if current >= start_date else []


def _generate_fixed_entries(db: Session, user: User, month_start: date) -> list[dict]:
    entries = []
    for item in sorted(
        db.scalars(select(FixedExpenseItem).where(FixedExpenseItem.user_id == user.id)).all(),
        key=lambda expense: (expense.name or "").lower(),
    ):
        start = item.start_date or month_start
        for occurrence in _occurrences_for_month(
            start,
            item.frequency or "monthly",
            month_start,
            second_day_of_month=item.second_date.day if item.second_date else item.second_day_of_month,
            preferred_day=item.due_day,
            days_of_week=item.days_of_week,
            monthly_week_numbers=item.monthly_week_numbers,
            monthly_weekday=item.monthly_weekday,
        ):
            _append_generated_entry(
                entries,
                occurrence,
                item.name,
                item.amount,
                "expense",
                "fixed",
                "Fixed expense",
                item.notes,
                item.id,
            )
    return entries


def _generate_loan_cash_entries(db: Session, user: User, month_start: date) -> list[dict]:
    entries = []
    for item in sorted(
        db.scalars(select(FixedExpenseItem).where(FixedExpenseItem.user_id == user.id, FixedExpenseItem.is_loan.is_(True))).all(),
        key=lambda expense: (expense.name or "").lower(),
    ):
        start = item.start_date or month_start
        for occurrence in _occurrences_for_month(
            start,
            item.frequency or "monthly",
            month_start,
            second_day_of_month=item.second_date.day if item.second_date else item.second_day_of_month,
            preferred_day=item.due_day,
            days_of_week=item.days_of_week,
            monthly_week_numbers=item.monthly_week_numbers,
            monthly_weekday=item.monthly_weekday,
        ):
            _append_generated_entry(
                entries,
                occurrence,
                item.name,
                item.amount,
                "expense",
                "fixed",
                item.category_label or "Loan payment",
                item.notes,
                item.id,
            )
    return entries


def _generate_variable_entries(db: Session, user: User, month_start: date) -> list[dict]:
    month_start, month_end = _month_range(month_start)
    entries = []
    planning_day = min(20, month_end.day)
    for item in sorted(
        db.scalars(select(VariableExpenseItem).where(VariableExpenseItem.user_id == user.id)).all(),
        key=lambda expense: (expense.name or "").lower(),
    ):
        if item.use_specific_date:
            start = item.specific_date or month_start.replace(day=planning_day)
            if item.frequency != "monthly" and not item.specific_date:
                start = month_start
            occurrences = _occurrences_for_month(
                start,
                item.frequency or "monthly",
                month_start,
                days_of_week=item.days_of_week,
            )
            weekday_multiplier = len(weekday_values(item.days_of_week)) if item.frequency not in {"monthly", "weekly", "biweekly"} else 0
            amount = item.amount * (weekday_multiplier or 1)
            for occurrence in occurrences:
                _append_generated_entry(
                    entries,
                    occurrence,
                    item.name,
                    amount,
                    "expense",
                    "variable",
                    "Variable plan",
                    item.notes,
                    item.id,
                )
            continue

        _append_generated_entry(
            entries,
            month_start.replace(day=planning_day),
            item.name,
            monthly_amount_for_variable_item(item),
            "expense",
            "variable",
            "Variable plan",
            item.notes,
            item.id,
        )
    return entries


def _generated_entries_between(db: Session, user: User, generator, start: date, end: date) -> list[dict]:
    month_cursor = start.replace(day=1)
    last_month = end.replace(day=1)
    entries = []
    while month_cursor <= last_month:
        entries.extend(item for item in generator(db, user, month_cursor) if start <= item["date"] <= end)
        month_cursor = add_months(month_cursor, 1)
    return entries


def fixed_expense_total(db: Session, user: User, target_date: date | None = None) -> float:
    from app.services.subscription_service import active_subscription_rows

    items = db.scalars(select(FixedExpenseItem).where(FixedExpenseItem.user_id == user.id)).all()
    if items:
        start, end = month_bounds(target_date)
        worksheet_total = sum(entry["amount"] for entry in _generated_entries_between(db, user, _generate_fixed_entries, start, end))
    else:
        worksheet_total = user.profile.fixed_expenses if user.profile else 0.0
    subscription_total = sum(row["amount"] for row in active_subscription_rows(db, user, purpose="monthly_plan"))
    return worksheet_total + subscription_total


@dataclass
class TaxEstimate:
    annual_gross_income: float
    taxable_income: float
    federal_income_tax: float
    state_income_tax: float
    social_security_tax: float
    medicare_tax: float
    additional_medicare_tax: float
    additional_tax_label: str
    additional_tax_type: str
    additional_tax_rate: float
    additional_tax_annual: float
    additional_tax_monthly: float
    annual_total: float
    monthly_total: float
    filing_status: str
    state: str | None
    state_rate: float
    state_method: str
    state_taxable_income: float
    state_standard_deduction: float
    state_personal_exemption: float
    state_credit: float
    state_brackets: list[tuple]
    state_note: str
    state_source_url: str | None
    federal_brackets: list[tuple]
    standard_deduction: float


def _tax_from_brackets(taxable_income: float, brackets: list[tuple]) -> float:
    taxable_income = max(taxable_income, 0)
    selected = brackets[0]
    for bracket in brackets:
        lower, upper, *_ = bracket
        if taxable_income >= lower and (upper is None or taxable_income <= upper):
            selected = bracket
            break
    lower, _upper, base_tax, rate = selected
    return base_tax + max(taxable_income - lower, 0) * rate


def _marginal_tax_from_thresholds(taxable_income: float, brackets: list[tuple[float, float]]) -> float:
    taxable_income = max(taxable_income, 0)
    if not brackets:
        return 0
    ordered = sorted(brackets, key=lambda bracket: bracket[0])
    tax = 0.0
    for index, (lower, rate) in enumerate(ordered):
        upper = ordered[index + 1][0] if index + 1 < len(ordered) else None
        if taxable_income <= lower:
            continue
        taxable_slice = (min(taxable_income, upper) if upper is not None else taxable_income) - lower
        tax += max(taxable_slice, 0) * rate
    return max(tax, 0)


def _state_tax_for_profile(state: str | None, filing_status: str, annual_gross_income: float) -> dict:
    if not state:
        return {
            "tax": 0,
            "method": "State not selected",
            "rate": 0,
            "taxable_income": 0,
            "deduction": 0,
            "exemption": 0,
            "credit": 0,
            "brackets": [],
            "note": "Select a tax state in Income Planning so ClearPath can estimate state paycheck withholding.",
            "source_url": None,
        }

    rule = STATE_TAX_RULES_2026.get(state)
    if not rule:
        return {
            "tax": 0,
            "method": "State table not installed",
            "rate": 0,
            "taxable_income": 0,
            "deduction": 0,
            "exemption": 0,
            "credit": 0,
            "brackets": [],
            "note": "ClearPath does not yet have a 2026 table for this state.",
            "source_url": None,
        }

    if rule["type"] == "none":
        return {
            "tax": 0,
            "method": "No broad wage income tax",
            "rate": 0,
            "taxable_income": 0,
            "deduction": 0,
            "exemption": 0,
            "credit": 0,
            "brackets": [],
            "note": rule["note"],
            "source_url": rule["source_url"],
        }

    is_joint = filing_status == "married_joint"
    deduction = rule["joint_deduction"] if is_joint else rule["single_deduction"]
    exemption = rule["joint_exemption"] if is_joint else rule["single_exemption"]
    credit = rule["joint_credit"] if is_joint else rule["single_credit"]
    brackets = rule["joint_brackets"] if is_joint else rule["brackets"]
    state_taxable_income = max(annual_gross_income - deduction - exemption, 0)
    state_tax = max(_marginal_tax_from_thresholds(state_taxable_income, brackets) - credit, 0)
    blended_rate = (state_tax / annual_gross_income * 100) if annual_gross_income else 0
    return {
        "tax": state_tax,
        "method": "2026 state wage income tax table",
        "rate": blended_rate,
        "taxable_income": state_taxable_income,
        "deduction": deduction,
        "exemption": exemption,
        "credit": credit,
        "brackets": brackets,
        "note": rule["note"],
        "source_url": rule["source_url"],
    }


def calculate_tax_estimate(profile: OnboardingProfile | None) -> TaxEstimate:
    filing_status = (profile.tax_filing_status if profile else None) or "married_joint"
    if filing_status not in TAX_FILING_STATUS_OPTIONS:
        filing_status = "married_joint"
    annual_gross_income = max(monthly_income_from_profile(profile) * 12 - retirement_taxable_income_adjustment(profile), 0)
    income_basis = (getattr(profile, "income_basis", None) if profile else None) or "take_home"
    additional_tax_label = ((getattr(profile, "tax_additional_label", None) if profile else None) or "Additional Local Tax").strip()
    additional_tax_type = (getattr(profile, "tax_additional_type", None) if profile else None) or "amount"
    if additional_tax_type not in {"amount", "percent"}:
        additional_tax_type = "amount"
    additional_tax_rate = max(float((getattr(profile, "tax_additional_rate", 0) if profile else 0) or 0), 0)
    additional_tax_monthly_amount = max(float((getattr(profile, "tax_additional_monthly_amount", 0) if profile else 0) or 0), 0)
    standard_deduction = STANDARD_DEDUCTIONS_2026[filing_status]
    taxable_income = max(annual_gross_income - standard_deduction, 0)
    federal_brackets = FEDERAL_TAX_BRACKETS_2026[filing_status]
    if income_basis != "gross":
        return TaxEstimate(
            annual_gross_income=annual_gross_income,
            taxable_income=0,
            federal_income_tax=0,
            state_income_tax=0,
            social_security_tax=0,
            medicare_tax=0,
            additional_medicare_tax=0,
            additional_tax_label=additional_tax_label,
            additional_tax_type=additional_tax_type,
            additional_tax_rate=additional_tax_rate,
            additional_tax_annual=0,
            additional_tax_monthly=0,
            annual_total=0,
            monthly_total=0,
            filing_status=filing_status,
            state=(profile.tax_state if profile else None) or None,
            state_rate=0,
            state_method="Take-home income entered",
            state_taxable_income=0,
            state_standard_deduction=0,
            state_personal_exemption=0,
            state_credit=0,
            state_brackets=[],
            state_note="Tax withholding is not added because your Income Planning is set to Take-Home Income.",
            state_source_url=None,
            federal_brackets=federal_brackets,
            standard_deduction=standard_deduction,
        )

    federal_income_tax = _tax_from_brackets(taxable_income, federal_brackets)

    state = (profile.tax_state if profile else None) or None
    state_result = _state_tax_for_profile(state, filing_status, annual_gross_income)
    state_income_tax = state_result["tax"]

    include_payroll_taxes = True if not profile else bool(profile.include_payroll_taxes)
    social_security_tax = min(annual_gross_income, SOCIAL_SECURITY_WAGE_BASE_2026) * SOCIAL_SECURITY_RATE_2026 if include_payroll_taxes else 0
    medicare_tax = annual_gross_income * MEDICARE_RATE_2026 if include_payroll_taxes else 0
    additional_threshold = ADDITIONAL_MEDICARE_THRESHOLDS[filing_status]
    additional_medicare_tax = max(annual_gross_income - additional_threshold, 0) * ADDITIONAL_MEDICARE_RATE if include_payroll_taxes else 0
    if additional_tax_type == "percent":
        additional_tax_annual = annual_gross_income * (additional_tax_rate / 100)
        additional_tax_monthly = additional_tax_annual / 12
    else:
        additional_tax_monthly = additional_tax_monthly_amount
        additional_tax_annual = additional_tax_monthly * 12
    annual_total = federal_income_tax + state_income_tax + social_security_tax + medicare_tax + additional_medicare_tax + additional_tax_annual
    return TaxEstimate(
        annual_gross_income=annual_gross_income,
        taxable_income=taxable_income,
        federal_income_tax=federal_income_tax,
        state_income_tax=state_income_tax,
        social_security_tax=social_security_tax,
        medicare_tax=medicare_tax,
        additional_medicare_tax=additional_medicare_tax,
        additional_tax_label=additional_tax_label,
        additional_tax_type=additional_tax_type,
        additional_tax_rate=additional_tax_rate,
        additional_tax_annual=additional_tax_annual,
        additional_tax_monthly=additional_tax_monthly,
        annual_total=annual_total,
        monthly_total=annual_total / 12,
        filing_status=filing_status,
        state=state,
        state_rate=state_result["rate"],
        state_method=state_result["method"],
        state_taxable_income=state_result["taxable_income"],
        state_standard_deduction=state_result["deduction"],
        state_personal_exemption=state_result["exemption"],
        state_credit=state_result["credit"],
        state_brackets=state_result["brackets"],
        state_note=state_result["note"],
        state_source_url=state_result["source_url"],
        federal_brackets=federal_brackets,
        standard_deduction=standard_deduction,
    )


# --- Pay-period scheduling -------------------------------------------------


def _advance_pay_date(pay_date: date, cadence: str | None) -> date:
    cadence = cadence or "monthly"
    if cadence == "weekly":
        return pay_date + timedelta(days=7)
    if cadence == "biweekly":
        return pay_date + timedelta(days=14)
    if cadence == "semimonthly":
        if pay_date.day <= 15:
            return _coerce_month_day(pay_date.replace(day=1), 28)
        return add_months(pay_date, 1).replace(day=15)
    if cadence == "annual":
        return date(pay_date.year + 1, pay_date.month, min(pay_date.day, calendar.monthrange(pay_date.year + 1, pay_date.month)[1]))
    if cadence == "irregular":
        return pay_date + timedelta(days=30)
    return add_months(pay_date, 1).replace(day=min(pay_date.day, calendar.monthrange(add_months(pay_date, 1).year, add_months(pay_date, 1).month)[1]))


def _previous_pay_date(pay_date: date, cadence: str | None) -> date:
    cadence = cadence or "monthly"
    if cadence == "weekly":
        return pay_date - timedelta(days=7)
    if cadence == "biweekly":
        return pay_date - timedelta(days=14)
    if cadence == "semimonthly":
        if pay_date.day <= 15:
            previous_month = add_months(pay_date, -1)
            return _coerce_month_day(previous_month, 28)
        return pay_date.replace(day=15)
    if cadence == "annual":
        return date(pay_date.year - 1, pay_date.month, min(pay_date.day, calendar.monthrange(pay_date.year - 1, pay_date.month)[1]))
    if cadence == "irregular":
        return pay_date - timedelta(days=30)
    previous_month = add_months(pay_date, -1)
    return previous_month.replace(day=min(pay_date.day, calendar.monthrange(previous_month.year, previous_month.month)[1]))


def current_pay_period_bounds(profile: OnboardingProfile | None, target_date: date | None = None) -> dict:
    target_date = target_date or app_today()
    cadence = (profile.paycheck_cadence if profile else None) or "monthly"
    next_pay_date = profile.next_pay_date if profile and profile.next_pay_date else target_date + timedelta(days=_period_delta_days(cadence))

    while next_pay_date <= target_date:
        next_pay_date = _advance_pay_date(next_pay_date, cadence)

    start_date = _previous_pay_date(next_pay_date, cadence)
    end_date = next_pay_date - timedelta(days=1)
    return {"start": start_date, "end": end_date, "next_pay_date": next_pay_date}


def planned_income_for_period(profile: OnboardingProfile | None, period_start: date, period_end: date) -> float:
    if not profile:
        return 0.0
    cadence = profile.paycheck_cadence or "monthly"
    period_days = (period_end - period_start).days + 1
    month_start, month_end = month_bounds(period_start)
    month_days = (month_end - month_start).days + 1
    if (profile.income_type or "salary") == "salary":
        if cadence != "irregular":
            base_income = annual_salary_from_profile(profile) / payments_per_year(cadence)
        else:
            base_income = (annual_salary_from_profile(profile) / 12) * (period_days / month_days)
    else:
        base_income = (profile.income_amount or 0) * (profile.hourly_hours_per_week or 40) * period_days / 7
    additional_income = additional_monthly_income_from_profile(profile) * (period_days / month_days)
    return base_income + additional_income


def loan_category_for_item(item: FixedExpenseItem) -> str | None:
    category = normalize_text(" ".join([item.category_label or "", item.name or ""]))
    if "mortgage" in category:
        return "mortgage"
    if getattr(item, "is_loan", False):
        return "loan"
    if any(token in category for token in ["loan", "vehicle payment", "auto payment", "car payment", "credit card", "debt", "heloc", "line of credit"]):
        return "loan"
    return None


# --- Transaction matching and queries --------------------------------------


def account_is_liability(account: Account) -> bool:
    account_type = normalize_text(account.account_type or "")
    normalized_type = account_type.replace("_", " ")
    if account_type in LIABILITY_ACCOUNT_TYPES or normalized_type in LIABILITY_ACCOUNT_TYPES:
        return True
    if any(keyword in normalized_type for keyword in LIABILITY_ACCOUNT_LABEL_KEYWORDS):
        return True
    account_label = normalize_text(f"{account.name or ''} {account.institution or ''}")
    return any(keyword in account_label for keyword in LIABILITY_ACCOUNT_LABEL_KEYWORDS)


def transaction_is_credit_card_payment(transaction: Transaction) -> bool:
    category = transaction.category
    if category and (category.name or "").strip().lower() == CREDIT_CARD_PAYMENT_CATEGORY_NAME.lower():
        return True
    return looks_like_credit_card_payment(
        transaction.description,
        transaction.merchant,
        transaction.source_name,
        transaction.account.name if transaction.account else None,
        transaction.account.account_type if transaction.account else None,
    )


def category_counts_as_spending(category: Category | None) -> bool:
    return not category or category.kind == "expense"


def category_is_active_budget(db: Session, category: Category | None, user: User | None = None, planning_labels: set[str] | None = None) -> bool:
    if not category:
        return False
    category_kind = category.kind or "expense"
    label = normalize_text(category.name or "")
    if category_kind == "income":
        return label == "income"
    if category_kind != "expense" or label == "other":
        return False
    if category.is_default:
        return False
    if (category.monthly_target or 0) > 0:
        return True
    if category.budget_sort_order is not None or (category.budget_group_key or "").strip():
        return True
    if planning_labels is not None:
        return label in planning_labels
    if not user:
        return False
    planning_labels = {
        normalize_text(getattr(item, "category_label", "") or "")
        for item in [
            *db.scalars(select(FixedExpenseItem).where(FixedExpenseItem.user_id == user.id)).all(),
            *db.scalars(select(VariableExpenseItem).where(VariableExpenseItem.user_id == user.id)).all(),
            *db.scalars(select(ForecastItem).where(ForecastItem.user_id == user.id, ForecastItem.item_type == "expense")).all(),
            *db.scalars(select(RecurringForecastTemplate).where(RecurringForecastTemplate.user_id == user.id, RecurringForecastTemplate.item_type == "expense")).all(),
        ]
        if normalize_text(getattr(item, "category_label", "") or "")
    }
    return label in planning_labels


def transaction_counts_as_spending(transaction: Transaction) -> bool:
    if transaction.splits:
        return True
    return category_counts_as_spending(transaction.category)


def transaction_counts_as_income(transaction: Transaction) -> bool:
    # Flask 1a91183: credit-card payments and liability-account inflows are
    # debt paydown, not income.
    if transaction_is_credit_card_payment(transaction):
        return False
    if transaction.account and account_is_liability(transaction.account):
        return False
    return not transaction.category or transaction.category.kind == "income"


def credit_card_debt_paydown_between(db: Session, user: User, start: date, end: date) -> float:
    transactions = [
        transaction
        for transaction in db.scalars(_transactions_between(db, user, start, end)).all()
        if transaction_is_credit_card_payment(transaction)
    ]
    liability_side_payments = [
        transaction
        for transaction in transactions
        if (transaction.amount or 0) > 0 and transaction.account and account_is_liability(transaction.account)
    ]
    if liability_side_payments:
        return float(sum(transaction.amount or 0 for transaction in liability_side_payments))
    return float(sum(abs(transaction.amount or 0) for transaction in transactions if (transaction.amount or 0) < 0))


def _transaction_matches_planned_item(transaction: Transaction, item_name: str) -> bool:
    item_text = normalize_text(item_name)
    category_text = normalize_text(transaction.category.name if transaction.category else "")
    description_text = normalize_text(transaction.description)
    merchant_text = normalize_text(transaction.merchant or "")
    return item_text and (
        item_text == category_text
        or item_text in description_text
        or item_text in merchant_text
    )


def _transaction_matches_subscription(transaction: Transaction, subscription) -> bool:
    return (
        _transaction_matches_planned_item(transaction, subscription.name)
        or normalize_text(subscription.merchant_key) in normalize_text(transaction.description)
        or normalize_text(subscription.merchant_key) in normalize_text(transaction.merchant or "")
    )


def _subscription_planned_amount_for_period(subscription, start_date: date, end_date: date, *, use_cash_timing: bool) -> float:
    if not use_cash_timing:
        return subscription.monthly_amount

    charge_amount = subscription.amount or subscription.monthly_amount
    cycle_days = max(subscription.cycle_days or 30, 1)
    next_charge = subscription.next_charge_date or subscription.last_seen or subscription.first_seen
    if not next_charge:
        return 0.0

    while next_charge < start_date:
        next_charge += timedelta(days=cycle_days)

    planned = 0.0
    while next_charge <= end_date:
        planned += charge_amount
        next_charge += timedelta(days=cycle_days)
    return planned


def _transactions_between(db: Session, user: User, start: date, end: date):
    return (
        select(Transaction)
        .options(joinedload(Transaction.category), joinedload(Transaction.account))
        .where(Transaction.user_id == user.id, Transaction.posted_date >= start, Transaction.posted_date <= end)
        .order_by(Transaction.posted_date.desc(), Transaction.id.desc())
    )


def _expense_transactions_between(db: Session, user: User, start: date, end: date) -> list[Transaction]:
    return [
        transaction
        for transaction in db.scalars(_transactions_between(db, user, start, end).where(Transaction.amount < 0)).all()
        if transaction_counts_as_spending(transaction)
    ]


def _month_expense_transactions(db: Session, user: User, target_date: date | None = None) -> list[Transaction]:
    start, end = month_bounds(target_date)
    return _expense_transactions_between(db, user, start, end)


def _income_transactions_between(db: Session, user: User, start: date, end: date) -> list[Transaction]:
    return [
        transaction
        for transaction in db.scalars(_transactions_between(db, user, start, end).where(Transaction.amount > 0)).all()
        if transaction_counts_as_income(transaction)
    ]


def _sort_plan_detail_rows(rows: list[dict]) -> list[dict]:
    return sorted(rows, key=lambda row: (max(row["planned"], row["actual"]), row["label"].lower()), reverse=True)


# --- Projected paychecks and income replacement -----------------------------


def _projected_paycheck_amount(profile: OnboardingProfile) -> float:
    cadence = profile.paycheck_cadence or "monthly"
    payment_count = max(payments_per_year(cadence), 1)
    income_type = profile.income_type or "salary"
    if income_type == "bonus" and cadence != "irregular":
        gross_amount = profile.income_amount or 0
        annualized_paycheck_income = gross_amount * payment_count
    elif income_type == "salary" and cadence != "irregular":
        gross_amount = annual_salary_from_profile(profile) / payment_count
        annualized_paycheck_income = annual_salary_from_profile(profile)
    else:
        annual_income = monthly_income_from_profile(profile) * 12
        gross_amount = annual_income / payment_count
        annualized_paycheck_income = annual_income

    if (profile.income_basis or "take_home") != "gross":
        return gross_amount

    annual_income = max(monthly_income_from_profile(profile) * 12, 0)
    if not annual_income:
        return gross_amount

    tax_share = min(max(annualized_paycheck_income / annual_income, 0), 1)
    estimated_withholding = (calculate_tax_estimate(profile).annual_total * tax_share) / payment_count
    return max(gross_amount - estimated_withholding, 0)


def _income_replacement_templates(db: Session, user: User, through_date: date | None = None) -> list[RecurringForecastTemplate]:
    query = select(RecurringForecastTemplate).where(
        RecurringForecastTemplate.user_id == user.id,
        RecurringForecastTemplate.item_type == "income",
        RecurringForecastTemplate.income_replacement.is_(True),
    )
    if through_date:
        query = query.where(RecurringForecastTemplate.start_date <= through_date)
    return db.scalars(query.order_by(RecurringForecastTemplate.start_date.asc(), RecurringForecastTemplate.id.asc())).all()


def _profile_from_income_replacement_template(base_profile: OnboardingProfile, template: RecurringForecastTemplate) -> OnboardingProfile:
    profile = OnboardingProfile()
    profile.income_amount = template.amount or 0
    profile.monthly_income = 0
    profile.income_basis = template.income_basis or base_profile.income_basis or "take_home"
    profile.income_type = template.income_type or base_profile.income_type or "salary"
    profile.paycheck_cadence = template.paycheck_cadence or template.frequency or base_profile.paycheck_cadence or "monthly"
    profile.income_frequency = profile.paycheck_cadence
    profile.next_pay_date = template.income_next_pay_date or template.start_date
    profile.hourly_hours_per_week = template.hourly_hours_per_week or base_profile.hourly_hours_per_week or 40
    profile.additional_income_amount = template.additional_income_amount or 0
    profile.additional_income_frequency = template.additional_income_frequency or "annual"
    profile.tax_state = template.tax_state or base_profile.tax_state
    profile.tax_filing_status = template.tax_filing_status or base_profile.tax_filing_status or "married_joint"
    profile.tax_gross_annual_income = base_profile.tax_gross_annual_income or 0
    profile.tax_state_effective_rate = base_profile.tax_state_effective_rate or 0
    profile.tax_additional_label = base_profile.tax_additional_label or "Additional Local Tax"
    profile.tax_additional_type = base_profile.tax_additional_type or "amount"
    profile.tax_additional_rate = base_profile.tax_additional_rate or 0
    profile.tax_additional_monthly_amount = base_profile.tax_additional_monthly_amount or 0
    profile.include_payroll_taxes = bool(template.include_payroll_taxes)
    profile.retirement_enabled = bool(base_profile.retirement_enabled)
    profile.retirement_has_employer_plan = bool(base_profile.retirement_has_employer_plan)
    profile.retirement_employer_withheld = bool(base_profile.retirement_employer_withheld)
    profile.retirement_monthly_contribution = base_profile.retirement_monthly_contribution or 0
    profile.retirement_has_personal_plan = bool(base_profile.retirement_has_personal_plan)
    profile.retirement_personal_monthly_contribution = base_profile.retirement_personal_monthly_contribution or 0
    return profile


def _active_income_replacement_template_for_date(templates: list[RecurringForecastTemplate], target_date: date) -> RecurringForecastTemplate | None:
    active_template = None
    for template in templates:
        if template.start_date <= target_date:
            active_template = template
        else:
            break
    return active_template


def _income_profile_for_date(base_profile: OnboardingProfile, templates: list[RecurringForecastTemplate], target_date: date) -> OnboardingProfile:
    active_template = _active_income_replacement_template_for_date(templates, target_date)
    if not active_template:
        return base_profile
    return _profile_from_income_replacement_template(base_profile, active_template)


def _income_profile_segments_between(db: Session, user: User, start: date, end: date) -> list[dict]:
    base_profile = user.profile
    if not base_profile:
        return []
    templates = _income_replacement_templates(db, user, end)
    boundaries = [start]
    boundaries.extend(template.start_date for template in templates if start < template.start_date <= end)
    boundaries.append(end + timedelta(days=1))
    segments = []
    for index, segment_start in enumerate(boundaries[:-1]):
        segment_end = boundaries[index + 1] - timedelta(days=1)
        if segment_start > segment_end:
            continue
        active_template = _active_income_replacement_template_for_date(templates, segment_start)
        segments.append(
            {
                "start": segment_start,
                "end": segment_end,
                "profile": _profile_from_income_replacement_template(base_profile, active_template) if active_template else base_profile,
                "source_id": active_template.id if active_template else None,
                "source_name": active_template.name if active_template else None,
                "template": active_template,
            }
        )
    return segments


def planned_income_for_period_with_future_adjustments(db: Session, user: User, period_start: date, period_end: date) -> float:
    if period_start > period_end:
        return 0.0
    month_start, month_end = month_bounds(period_start)
    month_days = (month_end - month_start).days + 1
    total = 0.0
    for segment in _income_profile_segments_between(db, user, period_start, period_end):
        segment_days = (segment["end"] - segment["start"]).days + 1
        total += monthly_income_from_profile(segment["profile"]) * (segment_days / month_days)
    return total


def planned_tax_for_period_with_future_adjustments(db: Session, user: User, period_start: date, period_end: date) -> float:
    if period_start > period_end:
        return 0.0
    month_start, month_end = month_bounds(period_start)
    month_days = (month_end - month_start).days + 1
    total = 0.0
    for segment in _income_profile_segments_between(db, user, period_start, period_end):
        profile = segment["profile"]
        if (profile.income_basis or "take_home") != "gross":
            continue
        segment_days = (segment["end"] - segment["start"]).days + 1
        total += calculate_tax_estimate(profile).monthly_total * (segment_days / month_days)
    return total


def _paycheck_entries_for_profile_between(
    profile: OnboardingProfile,
    start: date,
    end: date,
    source_id: int | str | None = None,
    description: str = "Projected paycheck",
    *,
    schedule_start: date | None = None,
    second_day_of_month: int | None = None,
    days_of_week: str | None = None,
    monthly_week_numbers: str | None = None,
    monthly_weekday: int | None = None,
) -> list[dict]:
    cadence = profile.paycheck_cadence or "monthly"
    if schedule_start and (second_day_of_month or days_of_week or monthly_week_numbers):
        amount = _projected_paycheck_amount(profile)
        entries = []
        month_cursor = start.replace(day=1)
        while month_cursor <= end.replace(day=1):
            for occurrence in _occurrences_for_month(
                schedule_start,
                cadence,
                month_cursor,
                second_day_of_month=second_day_of_month,
                days_of_week=days_of_week,
                monthly_week_numbers=monthly_week_numbers,
                monthly_weekday=monthly_weekday,
            ):
                if start <= occurrence <= end:
                    _append_generated_entry(entries, occurrence, description, amount, "income", "paycheck", "Income", source_id=source_id)
            month_cursor = add_months(month_cursor, 1)
        return entries

    next_pay_date = profile.next_pay_date or start
    while next_pay_date < start:
        next_pay_date = _advance_pay_date(next_pay_date, cadence)
    amount = _projected_paycheck_amount(profile)
    entries = []
    current = next_pay_date
    while current <= end:
        _append_generated_entry(entries, current, description, amount, "income", "paycheck", "Income", source_id=source_id)
        current = _advance_pay_date(current, cadence)
    return entries


def _paycheck_entries_between(db: Session, user: User, start: date, end: date) -> list[dict]:
    if not user.profile:
        return []
    entries = []
    for segment in _income_profile_segments_between(db, user, start, end):
        template = segment.get("template")
        entries.extend(
            _paycheck_entries_for_profile_between(
                segment["profile"],
                segment["start"],
                segment["end"],
                source_id=segment.get("source_id"),
                description=segment.get("source_name") or "Projected paycheck",
                schedule_start=(template.income_next_pay_date or template.start_date) if template else segment["profile"].next_pay_date,
                second_day_of_month=(
                    template.second_date.day
                    if template and template.second_date
                    else template.second_day_of_month
                    if template
                    else segment["profile"].paycheck_second_day_of_month
                ),
                days_of_week=template.days_of_week if template else segment["profile"].paycheck_days_of_week,
                monthly_week_numbers=template.monthly_week_numbers if template else segment["profile"].paycheck_monthly_week_numbers,
                monthly_weekday=template.monthly_weekday if template else segment["profile"].paycheck_monthly_weekday,
            )
        )
    return entries


# --- Recurring template and one-time generators ------------------------------


def _generate_recurring_template_entries(db: Session, user: User, month_start: date) -> list[dict]:
    entries = []
    templates = db.scalars(
        select(RecurringForecastTemplate)
        .where(RecurringForecastTemplate.user_id == user.id)
        .order_by(RecurringForecastTemplate.start_date.asc())
    ).all()
    for template in templates:
        if template.item_type == "income" and template.income_replacement:
            continue
        if template.item_type == "income" and template.income_type:
            profile = _profile_from_income_replacement_template(user.profile, template) if user.profile else None
            if profile:
                month_start_date, month_end_date = _month_range(month_start)
                entries.extend(
                    _paycheck_entries_for_profile_between(
                        profile,
                        month_start_date,
                        month_end_date,
                        source_id=template.id,
                        description=template.name,
                        schedule_start=template.income_next_pay_date or template.start_date,
                        second_day_of_month=template.second_date.day if template.second_date else template.second_day_of_month,
                        days_of_week=template.days_of_week,
                        monthly_week_numbers=template.monthly_week_numbers,
                        monthly_weekday=template.monthly_weekday,
                    )
                )
                continue
        for occurrence in _occurrences_for_month(
            template.start_date,
            template.frequency or "monthly",
            month_start,
            second_day_of_month=template.second_date.day if template.second_date else template.second_day_of_month,
            days_of_week=template.days_of_week,
            monthly_week_numbers=template.monthly_week_numbers,
            monthly_weekday=template.monthly_weekday,
        ):
            _append_generated_entry(entries, occurrence, template.name, template.amount, template.item_type, "recurring", template.category_label, template.notes, template.id)
    return entries


def _generate_one_time_entries(db: Session, user: User, month_start: date) -> list[dict]:
    month_start, month_end = _month_range(month_start)
    entries = []
    items = db.scalars(
        select(ForecastItem)
        .where(ForecastItem.user_id == user.id, ForecastItem.item_date >= month_start, ForecastItem.item_date <= month_end)
        .order_by(ForecastItem.item_date.asc(), ForecastItem.id.asc())
    ).all()
    for item in items:
        _append_generated_entry(entries, item.item_date, item.description, item.amount, item.item_type, "one_time", item.category_label, item.notes, item.id)
    return entries


def _account_is_cash_like(account: Account) -> bool:
    account_type = normalize_text(account.account_type or "")
    normalized_type = account_type.replace("_", " ")
    account_label = normalize_text(f"{account.name or ''} {account.institution or ''}")
    if account_is_liability(account):
        return False
    return (
        account_type in CASH_ACCOUNT_TYPES
        or normalized_type in CASH_ACCOUNT_TYPES
        or any(token in account_label for token in ["checking", "savings", "money market", "cash management"])
    )


def _account_is_savings_like(account: Account) -> bool:
    account_type = normalize_text(account.account_type or "")
    normalized_type = account_type.replace("_", " ")
    account_label = normalize_text(f"{account.name or ''} {account.institution or ''}")
    return (
        account_type in {"savings", "money market", "money_market"}
        or normalized_type in {"savings", "money market"}
        or any(token in account_label for token in ["savings", "money market"])
    )


def _account_is_operating_cash_account(account: Account) -> bool:
    account_type = normalize_text(account.account_type or "")
    normalized_type = account_type.replace("_", " ")
    account_label = normalize_text(f"{account.name or ''} {account.institution or ''}")
    if not _account_is_cash_like(account) or _account_is_savings_like(account):
        return False
    return (
        account_type in {"checking", "cash", "cash management", "cash_management"}
        or normalized_type in {"checking", "cash", "cash management"}
        or any(token in account_label for token in ["checking", "cash management"])
    )


def _account_is_depository_fallback(account: Account) -> bool:
    account_type = normalize_text(account.account_type or "")
    normalized_type = account_type.replace("_", " ")
    return _account_is_cash_like(account) and not _account_is_savings_like(account) and (
        account_type == "depository" or normalized_type == "depository"
    )


def _visible_plaid_items_for_cash_projection(db: Session, user: User) -> dict[int, PlaidItem]:
    return {
        item.id: item
        for item in db.scalars(
            select(PlaidItem).where(
                PlaidItem.user_id == user.id,
                PlaidItem.status != "disconnected",
                PlaidItem.disconnected_at.is_(None),
            )
        ).all()
    }


def _manual_account_is_available_for_cash_projection(account: Account) -> bool:
    if not account.is_manual:
        return False
    if (account.cash_projection_role or "auto") == "exclude":
        return False
    if account.plaid_item_id or account.plaid_account_id or account.mask:
        return False
    return not bool((account.institution or "").strip())


def _cash_projection_account_duplicate_key(account: Account) -> tuple:
    if account.is_manual:
        return "manual", account.id
    institution = normalize_text(account.institution or getattr(account, "_cash_projection_institution_name", "") or "")
    account_type = normalize_text(account.account_type or "").replace("_", " ")
    account_group = account_type
    if _account_is_savings_like(account):
        account_group = "savings"
    elif _account_is_operating_cash_account(account) or _account_is_depository_fallback(account):
        account_group = "operating_cash"
    elif _account_is_cash_like(account):
        account_group = "cash"
    mask = normalize_text(account.mask or "")
    if mask:
        return "plaid-mask", institution, account_group, mask
    return "plaid-name", institution, account_group, normalize_text(account.name or "")


def _cash_projection_account_preferred_sort(account: Account) -> tuple:
    updated_at = account.updated_at or account.created_at or datetime.min
    created_at = account.created_at or datetime.min
    return updated_at, created_at, account.id or 0


def _cash_projection_account_effective_role_for_group(accounts: list[Account]) -> str:
    roles = {account.cash_projection_role or "auto" for account in accounts}
    if "include" in roles:
        return "include"
    if "exclude" in roles:
        return "exclude"
    return "auto"


def _cash_projection_account_role(account: Account) -> str:
    return getattr(account, "_cash_projection_effective_role", None) or account.cash_projection_role or "auto"


def _dedupe_cash_projection_candidate_accounts(accounts: list[Account]) -> list[Account]:
    grouped: dict[tuple, list[Account]] = defaultdict(list)
    for account in accounts:
        grouped[_cash_projection_account_duplicate_key(account)].append(account)
    deduped = []
    for group in grouped.values():
        selected = max(group, key=_cash_projection_account_preferred_sort)
        selected._cash_projection_effective_role = _cash_projection_account_effective_role_for_group(group)
        deduped.append(selected)
    return sorted(deduped, key=lambda account: account.id or 0)


def cash_projection_candidate_accounts(db: Session, user: User) -> list[Account]:
    visible_items = _visible_plaid_items_for_cash_projection(db, user)
    accounts = db.scalars(select(Account).where(Account.user_id == user.id).order_by(Account.id.asc())).all()
    synced_candidates = []
    manual_candidates = []
    for account in accounts:
        if account.plaid_item_id and account.plaid_item_id in visible_items:
            account._cash_projection_institution_name = visible_items[account.plaid_item_id].institution_name
            synced_candidates.append(account)
            continue
        if _manual_account_is_available_for_cash_projection(account):
            manual_candidates.append(account)
    return _dedupe_cash_projection_candidate_accounts(synced_candidates or manual_candidates)


def cash_projection_account_is_manageable(db: Session, user: User, account: Account) -> bool:
    if account.user_id != user.id:
        return False
    return any(candidate.id == account.id for candidate in cash_projection_candidate_accounts(db, user))


def cash_projection_accounts(db: Session, user: User) -> list[Account]:
    accounts = cash_projection_candidate_accounts(db, user)
    included_accounts = [account for account in accounts if _cash_projection_account_role(account) == "include"]
    if included_accounts:
        return included_accounts
    cash_accounts = [
        account
        for account in accounts
        if _cash_projection_account_role(account) != "exclude" and _account_is_cash_like(account)
    ]
    operating_accounts = [account for account in cash_accounts if _account_is_operating_cash_account(account)]
    if operating_accounts:
        return operating_accounts
    depository_accounts = [account for account in cash_accounts if _account_is_depository_fallback(account)]
    return depository_accounts or cash_accounts


def cash_projection_balance_anchor(db: Session, user: User) -> dict:
    accounts = cash_projection_accounts(db, user)
    checking_accounts = [
        account
        for account in accounts
        if "checking" in normalize_text(f"{account.account_type or ''} {account.name or ''}")
    ]
    return {
        "date": app_today(),
        "balance": sum(account.current_balance or 0 for account in accounts),
        "checking_balance": sum(account.current_balance or 0 for account in checking_accounts),
        "account_count": len(accounts),
        "checking_account_count": len(checking_accounts),
        "included_accounts": [
            {
                "id": account.id,
                "name": account.name,
                "institution": account.institution,
                "account_type": account.account_type,
                "balance": account.current_balance or 0,
                "mask": account.mask,
                "cash_projection_role": _cash_projection_account_role(account),
            }
            for account in accounts
        ],
        "uses_cash_accounts": any(_account_is_cash_like(account) for account in accounts),
    }


def cash_projection_account_rows(db: Session, user: User) -> list[dict]:
    included_ids = {account.id for account in cash_projection_accounts(db, user)}
    accounts = sorted(
        cash_projection_candidate_accounts(db, user),
        key=lambda account: (normalize_text(account.institution or ""), normalize_text(account.name or ""), account.id or 0),
    )
    rows = []
    for account in accounts:
        role = _cash_projection_account_role(account)
        included = account.id in included_ids
        if role == "include":
            status_label, status_class, status_detail = "Included", "badge-green", "Manual"
        elif role == "exclude":
            status_label, status_class, status_detail = "Excluded", "badge-gray", "Manual"
        elif included:
            status_label, status_class, status_detail = "Included", "badge-blue", "Auto"
        else:
            status_label, status_class, status_detail = "Not Included", "badge-gray", "Auto"
        rows.append(
            {
                "account": account,
                "role": role,
                "included": included,
                "status_label": status_label,
                "status_class": status_class,
                "status_detail": status_detail,
            }
        )
    return rows


def cash_account_balance(db: Session, user: User, *, purpose: str = "forecast") -> float:
    assert_plaid_data_purpose(purpose)
    return sum(account.current_balance or 0 for account in cash_projection_accounts(db, user))


def _generated_entries_between(db: Session, user: User, generator, start: date, end: date) -> list[dict]:
    month_cursor = start.replace(day=1)
    last_month = end.replace(day=1)
    entries = []
    while month_cursor <= last_month:
        entries.extend(item for item in generator(db, user, month_cursor) if start <= item["date"] <= end)
        month_cursor = add_months(month_cursor, 1)
    return entries


def _actual_cash_transactions_between(db: Session, user: User, start: date, end: date) -> list[dict]:
    cash_account_ids = {account.id for account in cash_projection_accounts(db, user)}
    transactions = [
        transaction
        for transaction in db.scalars(_transactions_between(db, user, start, end)).unique().all()
        if transaction.account_id is None or transaction.account_id in cash_account_ids
    ]
    entries = []
    for transaction in _dedupe_cash_projection_transactions(transactions):
        _append_generated_entry(
            entries,
            transaction.posted_date,
            transaction.merchant or transaction.description,
            abs(transaction.amount),
            "income" if transaction.amount > 0 else "expense",
            "actual",
            transaction.category.name if transaction.category else None,
            transaction.notes,
            transaction.id,
        )
        entries[-1]["account_name"] = transaction.account.name if transaction.account else None
        entries[-1]["pending"] = bool(transaction.pending)
    return entries


def _dedupe_cash_projection_transactions(transactions: list[Transaction]) -> list[Transaction]:
    unique: list[Transaction] = []
    for transaction in sorted(transactions, key=lambda row: (row.posted_date, row.id or 0)):
        if any(_cash_projection_transactions_match(existing, transaction) for existing in unique):
            continue
        unique.append(transaction)
    return unique


def _cash_projection_transactions_match(first: Transaction, second: Transaction) -> bool:
    if first.id and second.id and first.id == second.id:
        return False
    if first.plaid_transaction_id and first.plaid_transaction_id == second.plaid_transaction_id:
        return True
    if first.import_hash and first.import_hash == second.import_hash:
        return True
    if transaction_duplicate_key(first) != transaction_duplicate_key(second):
        return False
    score = _transaction_description_match_score(first, second)
    if score >= 0.82:
        return True
    first_account = _transaction_cash_projection_account_label(first)
    second_account = _transaction_cash_projection_account_label(second)
    return bool(first_account and second_account and first_account == second_account and score >= 0.75)


def _transaction_cash_projection_account_label(transaction: Transaction) -> str:
    if transaction.account:
        return normalize_text(
            f"{transaction.account.institution or ''} {transaction.account.name or ''} {transaction.account.mask or ''}"
        )
    return normalize_text(transaction.source_name or "")


def _recurring_transaction_group_key(transaction: Transaction) -> tuple[str, str, float]:
    label = normalize_text(transaction.merchant or transaction.description or "")
    category_label = normalize_text(transaction.category.name if transaction.category else "")
    amount = round(abs(transaction.amount or 0), 2)
    return label, category_label, amount


def auto_recurring_detection_key(label: str | None, category_label: str | None, amount: float | int | None) -> str:
    normalized = "|".join(
        [normalize_text(label or ""), normalize_text(category_label or ""), f"{float(amount or 0):.2f}"]
    )
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _best_detected_recurring_frequency(dates: list[date]) -> str | None:
    if len(dates) < 2:
        return None
    intervals = [(dates[index] - dates[index - 1]).days for index in range(1, len(dates))]
    month_counts = Counter((posted.year, posted.month) for posted in dates)
    if max(month_counts.values(), default=0) >= 2 and all(10 <= interval <= 21 for interval in intervals):
        return "semimonthly"
    median = sorted(intervals)[len(intervals) // 2]
    for frequency, days, tolerance in [
        ("weekly", 7, 2),
        ("biweekly", 14, 3),
        ("monthly", 30, 7),
        ("quarterly", 91, 14),
        ("annual", 365, 30),
    ]:
        if abs(median - days) <= tolerance:
            return frequency
    return None


def _next_detected_recurring_date(last_seen: date, frequency: str) -> date:
    if frequency == "weekly":
        return last_seen + timedelta(days=7)
    if frequency in {"biweekly", "semimonthly"}:
        return last_seen + timedelta(days=14)
    if frequency == "quarterly":
        return add_months(last_seen, 3)
    if frequency == "annual":
        return date(last_seen.year + 1, last_seen.month, min(last_seen.day, calendar.monthrange(last_seen.year + 1, last_seen.month)[1]))
    return add_months(last_seen, 1)


def _manual_recurring_template_covers_detection(
    template: RecurringForecastTemplate, label: str, category_label: str, amount: float
) -> bool:
    if template.item_type != "expense":
        return False
    template_label = normalize_text(template.name or "")
    if template.category_label and category_label and normalize_text(template.category_label) != category_label:
        return False
    if abs(abs(template.amount or 0) - amount) > max(5.0, amount * 0.08):
        return False
    return bool(template_label and label and (template_label in label or label in template_label))


def detected_recurring_transaction_schedules(db: Session, user: User, as_of: date) -> list[dict]:
    history_start = as_of - timedelta(days=240)
    account_ids = {account.id for account in cash_projection_accounts(db, user) if account.id}
    query = (
        select(Transaction)
        .options(joinedload(Transaction.category))
        .where(
            Transaction.user_id == user.id,
            Transaction.amount < 0,
            Transaction.posted_date >= history_start,
            Transaction.posted_date <= as_of,
        )
        .order_by(Transaction.posted_date.asc(), Transaction.id.asc())
    )
    if account_ids:
        query = query.where(or_(Transaction.account_id.in_(account_ids), Transaction.account_id.is_(None)))
    grouped: dict[tuple[str, str, float], list[Transaction]] = defaultdict(list)
    for transaction in db.scalars(query).unique().all():
        if not transaction_counts_as_spending(transaction) or not transaction.category:
            continue
        label, category_label, amount = _recurring_transaction_group_key(transaction)
        if label and amount > 0:
            grouped[(label, category_label, amount)].append(transaction)
    manual_templates = db.scalars(
        select(RecurringForecastTemplate).where(
            RecurringForecastTemplate.user_id == user.id,
            RecurringForecastTemplate.item_type == "expense",
        )
    ).all()
    ignored_keys = set(
        db.scalars(
            select(CashProjectionRecurringIgnore.detection_key).where(CashProjectionRecurringIgnore.user_id == user.id)
        ).all()
    )
    schedules = []
    for (label, category_label, amount), transactions in grouped.items():
        if len(transactions) < 2:
            continue
        detection_key = auto_recurring_detection_key(label, category_label, amount)
        if detection_key in ignored_keys:
            continue
        if any(_manual_recurring_template_covers_detection(template, label, category_label, amount) for template in manual_templates):
            continue
        dates = sorted({transaction.posted_date for transaction in transactions if transaction.posted_date})
        if len(dates) < 2:
            continue
        frequency = _best_detected_recurring_frequency(dates)
        if not frequency:
            continue
        latest = max(transactions, key=lambda row: (row.posted_date, row.id or 0))
        schedules.append(
            {
                "name": latest.merchant or latest.description,
                "amount": amount,
                "frequency": frequency,
                "start_date": _next_detected_recurring_date(dates[-1], frequency),
                "second_day_of_month": dates[-1].day if frequency == "semimonthly" else None,
                "category_label": latest.category.name if latest.category else None,
                "notes": f"Auto-detected from {len(transactions)} similar transaction{'s' if len(transactions) != 1 else ''}.",
                "last_seen": dates[-1],
                "detection_key": detection_key,
            }
        )
    return sorted(schedules, key=lambda schedule: (-schedule["amount"], schedule["name"].lower()))


def detected_recurring_cash_schedule(
    db: Session, user: User, detection_key: str, as_of: date | None = None
) -> dict | None:
    cleaned_key = (detection_key or "").strip()
    if not cleaned_key:
        return None
    return next(
        (
            schedule
            for schedule in detected_recurring_transaction_schedules(db, user, as_of or app_today())
            if schedule["detection_key"] == cleaned_key
        ),
        None,
    )


def _generate_auto_recurring_transaction_entries(db: Session, user: User, month_start: date) -> list[dict]:
    entries = []
    for schedule in detected_recurring_transaction_schedules(db, user, app_today()):
        for occurrence in _occurrences_for_month(
            schedule["start_date"],
            schedule["frequency"],
            month_start.replace(day=1),
            second_day_of_month=schedule["second_day_of_month"],
        ):
            if occurrence <= app_today():
                continue
            _append_generated_entry(
                entries,
                occurrence,
                schedule["name"],
                schedule["amount"],
                "expense",
                "auto_recurring",
                schedule["category_label"],
                schedule["notes"],
                schedule["detection_key"],
            )
    return entries


def _cash_projection_schedule_entries_between(db: Session, user: User, start: date, end: date) -> list[dict]:
    if start > end:
        return []
    entries = []
    entries.extend(_generated_entries_between(db, user, _generate_recurring_template_entries, start, end))
    entries.extend(_generated_entries_between(db, user, _generate_loan_cash_entries, start, end))
    entries.extend(_generated_entries_between(db, user, _generate_auto_recurring_transaction_entries, start, end))
    entries.extend(_generated_entries_between(db, user, _generate_one_time_entries, start, end))
    return entries


def _planned_cash_entries_between(db: Session, user: User, start: date, end: date) -> list[dict]:
    if start > end:
        return []
    return [
        *_paycheck_entries_between(db, user, start, end),
        *_cash_projection_schedule_entries_between(db, user, start, end),
    ]


def _signed_cash_event_amount(event: dict) -> float:
    return event["amount"] if event["item_type"] == "income" else -abs(event["amount"])


def _planned_cash_event_matches_actual(planned: dict, actual: dict) -> bool:
    if planned["item_type"] != actual["item_type"]:
        return False
    tolerance = max(5.0, abs(planned["amount"]) * (0.15 if planned.get("source") == "paycheck" else 0.05))
    if abs(abs(planned["amount"]) - abs(actual["amount"])) > tolerance:
        return False
    if planned.get("source") == "paycheck":
        return True
    planned_label = normalize_text(planned.get("description") or "")
    actual_label = normalize_text(actual.get("description") or "")
    planned_category = normalize_text(planned.get("category_label") or "")
    actual_category = normalize_text(actual.get("category_label") or "")
    return bool(planned_label and actual_label and (planned_label in actual_label or actual_label in planned_label)) or bool(
        planned_category and planned_category == actual_category
    )


def _remaining_planned_cash_entries(planned_entries: list[dict], actual_entries: list[dict]) -> list[dict]:
    unmatched_actual_indexes = set(range(len(actual_entries)))
    remaining = []
    for planned in planned_entries:
        matched_index = next(
            (index for index in unmatched_actual_indexes if _planned_cash_event_matches_actual(planned, actual_entries[index])),
            None,
        )
        if matched_index is None:
            remaining.append(planned)
        else:
            unmatched_actual_indexes.remove(matched_index)
    return remaining


def _variable_spending_timing_insight(db: Session, user: User, month_start: date) -> dict:
    month_start, month_end = month_bounds(month_start)
    current_variable = sum(
        abs(transaction.amount)
        for transaction in _expense_transactions_between(db, user, month_start, min(app_today(), month_end))
    )
    prior_rows = []
    for offset in range(1, 4):
        prior_start = add_months(month_start, -offset)
        prior_end = prior_start.replace(day=calendar.monthrange(prior_start.year, prior_start.month)[1])
        midpoint = prior_start.replace(day=min(15, prior_end.day))
        first_half = sum(abs(row.amount) for row in _expense_transactions_between(db, user, prior_start, midpoint))
        total = sum(abs(row.amount) for row in _expense_transactions_between(db, user, prior_start, prior_end))
        if total > 0:
            prior_rows.append(first_half / total)
    average_first_half_share = sum(prior_rows) / len(prior_rows) if prior_rows else 0
    return {
        "current_variable_spend": current_variable,
        "planned_variable_spend": variable_expense_plan_total(db, user),
        "average_first_half_share": average_first_half_share,
        "affects_projection": False,
        "message": (
            "Prior months show variable spending tends to arrive earlier in the month."
            if average_first_half_share >= 0.6
            else "Prior months do not show a strong early-month variable spending pattern yet."
        ),
    }


def _week_rows_from_projection_days(days: list[dict]) -> list[dict]:
    weeks = []
    current_week = None
    for day in days:
        week_start = day["date"] - timedelta(days=day["date"].weekday())
        if not current_week or current_week["week_start"] != week_start:
            current_week = {
                "week_start": week_start,
                "days": [],
                "income": 0.0,
                "expenses": 0.0,
                "ending_balance": day["ending_balance"],
            }
            weeks.append(current_week)
        current_week["days"].append(day)
        current_week["income"] += sum(event["amount"] for event in day["events"] if event["item_type"] == "income")
        current_week["expenses"] += sum(event["amount"] for event in day["events"] if event["item_type"] != "income")
        current_week["ending_balance"] = day["ending_balance"]
    for week in weeks:
        week["week_end"] = week["days"][-1]["date"]
        week["net_change"] = week["income"] - week["expenses"]
    return weeks


def _add_months_preserving_day(target_date: date, months: int) -> date:
    month_index = target_date.month - 1 + months
    year = target_date.year + month_index // 12
    month = month_index % 12 + 1
    day = min(target_date.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _cash_projection_graph(days: list[dict], lowest_balance: dict, highest_balance: dict) -> dict:
    if not days:
        return {
            "points": "",
            "zero_axis_pct": 100,
            "show_zero_line": False,
            "min_value": 0,
            "max_value": 0,
            "month_markers": [],
            "point_rows": [],
        }
    min_value = min(lowest_balance["balance"], 0)
    max_value = max(highest_balance["balance"], 0)
    value_range = max(max_value - min_value, 1)
    x_denominator = max(len(days) - 1, 1)
    start_date = days[0]["date"]
    end_date = days[-1]["date"]
    points = []
    point_rows = []
    for index, day in enumerate(days):
        x = (index / x_denominator) * 100
        y = ((max_value - day["ending_balance"]) / value_range) * 100
        points.append(f"{x:.2f},{y:.2f}")
        point_rows.append(
            {
                "x_pct": round(x, 2),
                "y_pct": round(y, 2),
                "date_label": day["date"].strftime("%b %d, %Y"),
                "balance": day["ending_balance"],
                "balance_basis": day.get("balance_basis", "Projected"),
            }
        )
    month_markers = []
    offset = 1
    while True:
        marker_date = _add_months_preserving_day(start_date, offset)
        if marker_date > end_date:
            break
        day_index = (marker_date - start_date).days
        x = (day_index / x_denominator) * 100
        month_markers.append(
            {"label": marker_date.strftime("%b %d"), "axis_label": marker_date.strftime("%b %d"), "x_pct": round(x, 2)}
        )
        offset += 1
    zero_axis_pct = ((max_value - 0) / value_range) * 100
    return {
        "points": " ".join(points),
        "zero_axis_pct": zero_axis_pct,
        "show_zero_line": 2 < zero_axis_pct < 98,
        "min_value": min_value,
        "max_value": max_value,
        "month_markers": month_markers,
        "point_rows": point_rows,
    }


def _projection_calendar_cells(days: list[dict], start_date: date) -> list[dict | None]:
    calendar_cells = [None] * ((start_date.weekday() + 1) % 7) + days
    while len(calendar_cells) % 7:
        calendar_cells.append(None)
    return calendar_cells


def _projection_month_group(projection: dict, month_start: date, days: list[dict]) -> dict:
    first_day = days[0]["date"]
    last_day = days[-1]["date"]
    events = [event for day in days for event in day["events"]]
    is_full_month = first_day.day == 1 and last_day == month_bounds(first_day)[1]
    return {
        "month": month_start,
        "month_label": month_start.strftime("%B %Y") if is_full_month else f"{first_day.strftime('%b %d')} - {last_day.strftime('%b %d, %Y')}",
        "start_date": first_day,
        "end_date": last_day,
        "days": days,
        "calendar_cells": _projection_calendar_cells(days, first_day),
        "events": events,
        "start_balance": projection["start_balance"] if first_day == projection["start_date"] else days[0]["ending_balance"] - days[0]["net_change"],
        "end_balance": days[-1]["ending_balance"],
        "balance_anchor": projection["balance_anchor"],
        "lowest_balance": min(
            ({"date": day["date"], "balance": day["ending_balance"]} for day in days), key=lambda row: row["balance"]
        ),
        "highest_balance": max(
            ({"date": day["date"], "balance": day["ending_balance"]} for day in days), key=lambda row: row["balance"]
        ),
        "trend": projection["trend"],
        "graph": projection["graph"],
    }


def split_projection_into_months(projection: dict) -> list[dict]:
    grouped = []
    current_month = None
    current_days = []
    for day in projection.get("days", []):
        month_start = day["date"].replace(day=1)
        if current_month and month_start != current_month:
            grouped.append(_projection_month_group(projection, current_month, current_days))
            current_days = []
        current_month = month_start
        current_days.append(day)
    if current_month and current_days:
        grouped.append(_projection_month_group(projection, current_month, current_days))
    return grouped


def build_cash_projection_period(
    db: Session,
    user: User,
    start_date: date,
    end_date: date,
    starting_balance: float | None = None,
) -> dict:
    month_start = start_date.replace(day=1)
    today = app_today()
    balance_anchor = cash_projection_balance_anchor(db, user)
    uses_live_cash_anchor = starting_balance is None and balance_anchor["account_count"] > 0
    actual_today = _actual_cash_transactions_between(db, user, today, today)
    actual_end = min(end_date, today)
    range_actual_events = _actual_cash_transactions_between(db, user, start_date, actual_end) if start_date <= actual_end else []
    planned_start = max(start_date, today + timedelta(days=1) if uses_live_cash_anchor else today)
    range_planned_events = _planned_cash_entries_between(db, user, planned_start, end_date) if planned_start <= end_date else []
    if planned_start == today:
        planned_today = [event for event in range_planned_events if event["date"] == today]
        remaining_today = _remaining_planned_cash_entries(planned_today, actual_today)
        range_planned_events = [event for event in range_planned_events if event["date"] != today] + remaining_today
    events = sorted(
        range_actual_events + range_planned_events,
        key=lambda event: (event["date"], 0 if event["item_type"] == "income" else 1, event["description"]),
    )
    daily_events: dict[date, list[dict]] = defaultdict(list)
    for event in events:
        event["signed_amount"] = _signed_cash_event_amount(event)
        daily_events[event["date"]].append(event)
    if starting_balance is not None:
        balance = starting_balance
    elif start_date <= today:
        actual_events_to_anchor = _actual_cash_transactions_between(db, user, start_date, today)
        balance = balance_anchor["balance"] - sum(_signed_cash_event_amount(event) for event in actual_events_to_anchor)
    else:
        bridge_start = today + timedelta(days=1) if uses_live_cash_anchor else today
        bridge_planned = _planned_cash_entries_between(db, user, bridge_start, start_date - timedelta(days=1))
        bridge_planned_today = [event for event in bridge_planned if event["date"] == today]
        bridge_planned = [event for event in bridge_planned if event["date"] != today] + _remaining_planned_cash_entries(
            bridge_planned_today, actual_today
        )
        balance = balance_anchor["balance"] + sum(_signed_cash_event_amount(event) for event in bridge_planned)
    initial_balance = balance
    days = []
    lowest_balance = {"date": start_date, "balance": balance}
    highest_balance = {"date": start_date, "balance": balance}
    current = start_date
    while current <= end_date:
        day_events = daily_events.get(current, [])
        net_change = sum(event["signed_amount"] for event in day_events)
        balance += net_change
        scheduled_events = [event for event in day_events if event["source"] != "actual"]
        actual_events = [event for event in day_events if event["source"] == "actual"]
        if current < today:
            balance_basis = "Actual"
        elif current == today:
            balance_basis = "Projected EOD" if scheduled_events else "Current"
        else:
            balance_basis = "Projected"
        day_row = {
            "date": current,
            "day": current.day,
            "weekday": current.strftime("%a"),
            "is_today": current == today,
            "is_past": current < today,
            "events": day_events,
            "actual_events": actual_events,
            "scheduled_events": scheduled_events,
            "actual_balance": balance_anchor["balance"] if current == today and starting_balance is None else None,
            "balance_basis": balance_basis,
            "net_change": net_change,
            "actual_change": sum(event["signed_amount"] for event in actual_events),
            "scheduled_change": sum(event["signed_amount"] for event in scheduled_events),
            "ending_balance": balance,
        }
        days.append(day_row)
        if balance < lowest_balance["balance"]:
            lowest_balance = {"date": current, "balance": balance}
        if balance > highest_balance["balance"]:
            highest_balance = {"date": current, "balance": balance}
        current += timedelta(days=1)
    graph = _cash_projection_graph(days, lowest_balance, highest_balance)
    return {
        "month": month_start,
        "month_label": month_start.strftime("%B %Y") if start_date.day == 1 and end_date == month_bounds(start_date)[1] else f"{start_date.strftime('%b %d')} - {end_date.strftime('%b %d, %Y')}",
        "start_date": start_date,
        "end_date": end_date,
        "start_balance": initial_balance,
        "end_balance": days[-1]["ending_balance"] if days else initial_balance,
        "balance_anchor": balance_anchor,
        "lowest_balance": lowest_balance,
        "highest_balance": highest_balance,
        "days": days,
        "weeks": _week_rows_from_projection_days(days),
        "calendar_cells": _projection_calendar_cells(days, start_date),
        "events": events,
        "trend": _variable_spending_timing_insight(db, user, month_start),
        "graph": graph,
    }


def build_cash_projection_range(db: Session, user: User, start_month: date | None = None, months: int = 1) -> dict:
    months = min(max(int(months or 1), 1), 6)
    month_start = (start_month or app_today()).replace(day=1)
    end_month = add_months(month_start, months - 1)
    range_end = month_bounds(end_month)[1]
    full_projection = build_cash_projection_period(db, user, month_start, range_end)
    return {
        "start_month": month_start,
        "start_date": full_projection["start_date"],
        "end_date": full_projection["end_date"],
        "months": months,
        "projections": split_projection_into_months(full_projection),
        "days": full_projection["days"],
        "events": full_projection["events"],
        "start_balance": full_projection["start_balance"],
        "end_balance": full_projection["end_balance"],
        "balance_anchor": full_projection["balance_anchor"],
        "lowest_balance": full_projection["lowest_balance"],
        "highest_balance": full_projection["highest_balance"],
        "graph": full_projection["graph"],
    }


def build_three_month_forecast(
    db: Session,
    user: User,
    start_date: date | None = None,
    *,
    purpose: str = "forecast",
) -> list[dict]:
    assert_plaid_data_purpose(purpose)
    start_date = (start_date or app_today()).replace(day=1)
    profile = user.profile or OnboardingProfile(
        income_amount=0,
        income_frequency="monthly",
        monthly_income=0,
        fixed_expenses=0,
        planned_savings_contribution=0,
        planned_debt_payment=0,
        target_investment_contribution=0,
    )
    variable_plan_total = variable_expense_plan_total(db, user)
    planned_savings = planned_savings_contribution_for_user(db, user, profile)
    retirement_total = retirement_cash_flow_contribution(profile)
    loan_extra_total = selected_loan_extra_payment_total(db, user)
    running_cash = cash_account_balance(db, user, purpose=purpose)
    forecast = []
    for offset in range(3):
        month_start = add_months(start_date, offset)
        fixed_total = fixed_expense_total(db, user, month_start)
        month_end = month_bounds(month_start)[1]
        monthly_income = planned_income_for_period_with_future_adjustments(db, user, month_start, month_end)
        monthly_tax = planned_tax_for_period_with_future_adjustments(db, user, month_start, month_end)
        generated_entries = _cash_projection_schedule_entries_between(db, user, month_start, month_end)
        generated_entries.sort(key=lambda item: (-item["amount"], item["date"], item["description"].lower()))
        recurring_income = sum(item["amount"] for item in generated_entries if item["item_type"] == "income")
        recurring_expenses = sum(item["amount"] for item in generated_entries if item["item_type"] == "expense")
        one_time_income = sum(
            item["amount"] for item in generated_entries if item["item_type"] == "income" and item["source"] == "one_time"
        )
        one_time_expenses = sum(
            item["amount"] for item in generated_entries if item["item_type"] == "expense" and item["source"] == "one_time"
        )
        planned_income_total = recurring_income
        planned_expense_total = recurring_expenses
        required_outflow_total = (
            monthly_tax
            + planned_expense_total
            + planned_savings
            + profile.planned_debt_payment
            + retirement_total
            + loan_extra_total
        )
        forecast_income_total = monthly_income + planned_income_total
        forecast_expense_total = required_outflow_total
        _baseline_budget = (
            monthly_income
            - monthly_tax
            - fixed_total
            - planned_savings
            - profile.planned_debt_payment
            - retirement_total
            - loan_extra_total
            - variable_plan_total
        )
        planned_buffer = forecast_income_total - forecast_expense_total
        ending_cash = running_cash + planned_buffer
        forecast.append(
            {
                "month_start": month_start,
                "month_name": current_month_name(month_start),
                "baseline_income": monthly_income,
                "fixed_expenses": fixed_total,
                "planned_savings": planned_savings,
                "planned_debt": profile.planned_debt_payment + loan_extra_total,
                "planned_taxes": monthly_tax,
                "planned_retirement": retirement_total,
                "planned_variable": variable_plan_total,
                "planned_income": planned_income_total,
                "planned_expenses": planned_expense_total,
                "one_time_income": one_time_income,
                "one_time_expenses": one_time_expenses,
                "forecast_income_total": forecast_income_total,
                "forecast_expense_total": forecast_expense_total,
                "planned_buffer": planned_buffer,
                "starting_cash": running_cash,
                "ending_cash": ending_cash,
                "forecast_items": generated_entries,
            }
        )
        running_cash = ending_cash
    return forecast


def generate_cash_projection_calendar_token() -> str:
    return secrets.token_urlsafe(32)


def cash_projection_calendar_token_hash(token: str) -> str:
    return hashlib.sha256((token or "").strip().encode("utf-8")).hexdigest()


def _ics_escape(value) -> str:
    text = str(value or "")
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
        .replace("\r", "\\n")
    )


def _fold_ics_line(line: str) -> list[str]:
    if len(line) <= 73:
        return [line]
    lines = [line[:73]]
    remaining = line[73:]
    while remaining:
        lines.append(" " + remaining[:72])
        remaining = remaining[72:]
    return lines


def _calendar_source_label(source: str | None) -> str:
    return {
        "actual": "Actual cash transaction",
        "paycheck": "Income planning",
        "fixed": "Scheduled fixed item",
        "variable": "Scheduled variable item",
        "recurring": "Recurring forecast schedule",
        "auto_recurring": "Auto-detected recurring charge",
        "one_time": "One-time forecast item",
    }.get(source or "", "Scheduled cash item")


def _calendar_amount_label(event: dict) -> str:
    signed_amount = event["amount"] if event["item_type"] == "income" else -abs(event["amount"])
    sign = "+" if signed_amount >= 0 else "-"
    return f"{sign}${abs(signed_amount):,.2f}"


def _calendar_balance_label(amount: float | int | None) -> str:
    balance = float(amount or 0)
    return f"{'-' if balance < 0 else ''}${abs(balance):,.2f}"


def _calendar_signed_money_label(amount: float | int | None) -> str:
    value = float(amount or 0)
    return f"{'+' if value >= 0 else '-'}${abs(value):,.2f}"


def _calendar_cash_item_label(event: dict) -> str:
    label = f"{_calendar_amount_label(event)} {event.get('description') or 'Cash item'}"
    metadata = []
    if event.get("category_label"):
        metadata.append(f"Category: {event['category_label']}")
    if event.get("source") == "actual" and event.get("account_name"):
        metadata.append(f"Account: {event['account_name']}")
    elif event.get("source") and event.get("source") != "actual":
        metadata.append(f"Source: {_calendar_source_label(event.get('source'))}")
    if metadata:
        label = f"{label} ({'; '.join(metadata)})"
    return label


def _calendar_cash_event_lines(title: str, events: list[dict]) -> list[str]:
    return [title] + [f"* {_calendar_cash_item_label(event)}" for event in events] if events else []


def _shift_calendar_months(target_date: date, months: int) -> date:
    month_index = target_date.month - 1 + months
    year = target_date.year + month_index // 12
    month = month_index % 12 + 1
    day = min(target_date.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def cash_projection_calendar_history_months(user: User) -> int:
    from app.core.feature_access import user_has_plan_at_least

    return 6 if user_has_plan_at_least(user, "premium") else 3


def cash_projection_calendar_feed_window(user: User, anchor_date: date | None = None) -> tuple[date, date]:
    anchor = anchor_date or app_today()
    return (
        _shift_calendar_months(anchor, -cash_projection_calendar_history_months(user)),
        _shift_calendar_months(anchor, 6),
    )


def build_cash_projection_calendar_feed(
    db: Session,
    user: User,
    start_date: date | None = None,
    end_date: date | None = None,
) -> str:
    default_start_date, default_end_date = cash_projection_calendar_feed_window(user)
    start_was_provided = start_date is not None
    start_date = start_date or default_start_date
    if end_date is None:
        end_date = _shift_calendar_months(start_date, 6) if start_was_provided else default_end_date
    projection = build_cash_projection_period(db, user, start_date, end_date)
    now_stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    calendar_lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//ClearPath Finance//Cash Balance Projections//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:ClearPath Cash Balance Projections",
        "X-WR-CALDESC:Daily projected cash balances plus scheduled income and expenses from ClearPath Finance.",
        "REFRESH-INTERVAL;VALUE=DURATION:PT6H",
        "X-PUBLISHED-TTL:PT6H",
    ]
    today = app_today()
    for day in projection.get("days", []):
        day_date = day["date"]
        day_end_date = day_date + timedelta(days=1)
        balance_label = _calendar_balance_label(day.get("ending_balance"))
        basis = day.get("balance_basis") or "Projected"
        is_actual_day = day_date <= today
        relevant_events = day.get("actual_events", []) if is_actual_day else day.get("scheduled_events", [])
        expense_events = [event for event in relevant_events if event.get("item_type") != "income"]
        income_events = [event for event in relevant_events if event.get("item_type") == "income"]
        if expense_events:
            noun = "expense" if len(expense_events) == 1 else "expenses"
            if not is_actual_day:
                noun = "planned expense" if len(expense_events) == 1 else "planned expenses"
            expense_count_label = f" ({len(expense_events)} {noun})"
        else:
            expense_count_label = ""
        uid_seed = "|".join([str(user.id), day_date.isoformat(), "balance"])
        uid = f"cash-balance-{hashlib.sha256(uid_seed.encode('utf-8')).hexdigest()}@clearpath-finance"
        description_parts = [
            f"{basis} cash balance: {balance_label}",
            f"Net cash movement: {_calendar_signed_money_label(day.get('net_change'))}",
        ]
        if expense_events:
            expense_total = sum(_signed_cash_event_amount(event) for event in expense_events)
            description_parts.append(
                f"{'Actual' if is_actual_day else 'Planned'} expense total: {_calendar_signed_money_label(expense_total)}"
            )
            description_parts.extend(
                _calendar_cash_event_lines("Actual expenses:" if is_actual_day else "Planned expenses:", expense_events)
            )
        if income_events:
            income_total = sum(_signed_cash_event_amount(event) for event in income_events)
            description_parts.append(
                f"{'Actual' if is_actual_day else 'Planned'} income total: {_calendar_signed_money_label(income_total)}"
            )
            description_parts.extend(
                _calendar_cash_event_lines("Actual income items:" if is_actual_day else "Planned income items:", income_events)
            )
        if not expense_events and not income_events:
            description_parts.append("No planned or actual expenses are scheduled for this day.")
        description_parts.append(
            "This is a ClearPath cash balance projection. Review in ClearPath before relying on timing or amount."
        )
        calendar_lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{uid}",
                f"DTSTAMP:{now_stamp}",
                f"DTSTART;VALUE=DATE:{day_date.strftime('%Y%m%d')}",
                f"DTEND;VALUE=DATE:{day_end_date.strftime('%Y%m%d')}",
                f"SUMMARY:{_ics_escape(f'{basis} Balance: {balance_label}{expense_count_label}')}",
                f"DESCRIPTION:{_ics_escape(chr(10).join(description_parts))}",
                "TRANSP:TRANSPARENT",
                "END:VEVENT",
            ]
        )
    calendar_lines.append("END:VCALENDAR")
    return "\r\n".join(folded for line in calendar_lines for folded in _fold_ics_line(line)) + "\r\n"


# --- Plan-vs-actual detail rows ---------------------------------------------


def _planned_entries_by_label(entries: list[dict], *, item_type: str | None = None, source: str | None = None, unique_entries: bool = False) -> dict[str, dict]:
    planned_by_label: dict[str, dict] = {}
    for entry in entries:
        if item_type and entry["item_type"] != item_type:
            continue
        if source and entry["source"] != source:
            continue
        label = entry["description"]
        if unique_entries:
            label = f"{entry['description']}|{entry['source']}|{entry.get('source_id') or entry['date'].isoformat()}|{len(planned_by_label)}"
        detail = planned_by_label.setdefault(
            label,
            {
                "amount": 0.0,
                "source": entry["source"],
                "match_label": entry["description"],
                "display_label": entry["description"],
                "date": entry["date"],
                "source_ids": set(),
            },
        )
        detail["amount"] += entry["amount"]
        if entry.get("source_id"):
            detail["source_ids"].add(entry["source_id"])
    return planned_by_label


def _append_forecast_detail_rows(
    rows: list[dict],
    transactions: list[Transaction],
    matched_transaction_ids: set[int],
    planned_by_label: dict[str, dict],
) -> None:
    for label, planned_detail in planned_by_label.items():
        planned = planned_detail["amount"] if isinstance(planned_detail, dict) else planned_detail
        match_label = planned_detail.get("match_label", label) if isinstance(planned_detail, dict) else label
        matches = [
            txn
            for txn in transactions
            if txn.id not in matched_transaction_ids and _transaction_matches_planned_item(txn, match_label)
        ]
        matched_transaction_ids.update(txn.id for txn in matches)
        actual = sum(abs(txn.amount) for txn in matches)
        if planned or actual:
            display_label = planned_detail.get("display_label", label) if isinstance(planned_detail, dict) else label
            row = {
                "label": display_label,
                "planned": planned,
                "actual": actual,
                "diff": actual - planned,
                "transaction_ids": [txn.id for txn in matches],
            }
            if isinstance(planned_detail, dict) and len(planned_detail.get("source_ids", set())) == 1:
                source = planned_detail.get("source")
                row["source_id"] = next(iter(planned_detail["source_ids"]))
                if source == "one_time":
                    row["source"] = "forecast_item"
                elif source == "recurring":
                    row["source"] = "recurring_template"
            rows.append(row)


def income_plan_detail_rows(db: Session, user: User, planned_base_income: float, target_date: date | None = None, start_date: date | None = None, end_date: date | None = None) -> list[dict]:
    if not start_date or not end_date:
        start_date, end_date = month_bounds(target_date)

    transactions = _income_transactions_between(db, user, start_date, end_date)
    recurring_income = _planned_entries_by_label(
        _generated_entries_between(db, user, _generate_recurring_template_entries, start_date, end_date),
        item_type="income",
        source="recurring",
    )
    one_time_income = _planned_entries_by_label(
        _generated_entries_between(db, user, _generate_one_time_entries, start_date, end_date),
        item_type="income",
        source="one_time",
    )

    rows = []
    matched_transaction_ids: set[int] = set()
    _append_forecast_detail_rows(rows, transactions, matched_transaction_ids, recurring_income)
    _append_forecast_detail_rows(rows, transactions, matched_transaction_ids, one_time_income)

    baseline_actual = sum(txn.amount for txn in transactions if txn.id not in matched_transaction_ids)
    if planned_base_income or baseline_actual:
        rows.append(
            {
                "label": "Baseline Income",
                "planned": planned_base_income,
                "actual": baseline_actual,
                "diff": baseline_actual - planned_base_income,
            }
        )

    return _sort_plan_detail_rows(rows)


def _fixed_item_matches_transaction(transaction: Transaction, item: FixedExpenseItem) -> bool:
    return (
        _transaction_matches_planned_item(transaction, item.name)
        or (
            transaction.category
            and transaction.category.name in FIXED_EXPENSE_CATEGORY_NAMES
            and normalize_text(item.name) in normalize_text(transaction.category.name)
        )
    )


def _fixed_item_transaction_matches_by_id(db: Session, user: User, transactions: list[Transaction]) -> tuple[dict[int, list[Transaction]], set[int]]:
    matches_by_id: dict[int, list[Transaction]] = {}
    matched_transaction_ids: set[int] = set()
    for item in sorted(
        db.scalars(select(FixedExpenseItem).where(FixedExpenseItem.user_id == user.id)).all(),
        key=lambda expense: (expense.name or "").lower(),
    ):
        matches = [txn for txn in transactions if _fixed_item_matches_transaction(txn, item)]
        matches_by_id[item.id] = matches
        matched_transaction_ids.update(txn.id for txn in matches)
    return matches_by_id, matched_transaction_ids


def _fixed_plan_claimed_transaction_ids(
    db: Session,
    user: User,
    transactions: list[Transaction],
    *,
    include_subscriptions: bool = True,
    subscription_rows: list[dict] | None = None,
) -> set[int]:
    from app.services.subscription_service import active_subscription_rows

    _matches_by_id, matched_transaction_ids = _fixed_item_transaction_matches_by_id(db, user, transactions)
    if include_subscriptions:
        resolved_subscription_rows = subscription_rows if subscription_rows is not None else active_subscription_rows(db, user, purpose="monthly_plan")
        for subscription_row in resolved_subscription_rows:
            subscription = subscription_row["subscription"]
            matched_transaction_ids.update(
                txn.id
                for txn in transactions
                if txn.id not in matched_transaction_ids and _transaction_matches_subscription(txn, subscription)
            )
    return matched_transaction_ids


def fixed_plan_detail_rows(db: Session, user: User, target_date: date | None = None, start_date: date | None = None, end_date: date | None = None) -> list[dict]:
    from app.services.subscription_service import SUBSCRIPTION_CATEGORY, active_subscription_rows

    use_cash_timing = bool(start_date and end_date)
    if start_date and end_date:
        transactions = _expense_transactions_between(db, user, start_date, end_date)
    else:
        start_date, end_date = month_bounds(target_date)
        transactions = _month_expense_transactions(db, user, target_date)
    generated_entries = _generated_entries_between(db, user, _generate_fixed_entries, start_date, end_date)
    planned_by_label = defaultdict(float)
    for entry in generated_entries:
        planned_by_label[entry["description"]] += entry["amount"]
    recurring_planned_by_label = _planned_entries_by_label(
        _generated_entries_between(db, user, _generate_recurring_template_entries, start_date, end_date),
        item_type="expense",
        source="recurring",
    )
    rows = []
    fixed_item_matches_by_id, matched_transaction_ids = _fixed_item_transaction_matches_by_id(db, user, transactions)

    for item in sorted(
        db.scalars(select(FixedExpenseItem).where(FixedExpenseItem.user_id == user.id)).all(),
        key=lambda expense: (expense.name or "").lower(),
    ):
        matches = fixed_item_matches_by_id.get(item.id, [])
        actual = sum(abs(txn.amount) for txn in matches)
        planned = planned_by_label[item.name] if planned_by_label is not None else monthly_amount_for_fixed_item(item)
        if planned or actual:
            rows.append(
                {
                    "label": item.name,
                    "planned": planned,
                    "actual": actual,
                    "diff": actual - planned,
                    "source": "fixed_expense",
                    "source_id": item.id,
                    "category_label": item.category_label,
                    "loan_kind": loan_category_for_item(item),
                    "transaction_ids": [txn.id for txn in matches],
                }
            )

    _append_forecast_detail_rows(rows, transactions, matched_transaction_ids, recurring_planned_by_label)

    subscription_planned = 0.0
    subscription_actual = 0.0
    subscription_count = 0
    subscription_transaction_ids = []
    for subscription_row in active_subscription_rows(db, user, purpose="monthly_plan"):
        subscription = subscription_row["subscription"]
        matches = [
            txn
            for txn in transactions
            if txn.id not in matched_transaction_ids and _transaction_matches_subscription(txn, subscription)
        ]
        matched_transaction_ids.update(txn.id for txn in matches)
        subscription_transaction_ids.extend(txn.id for txn in matches)
        subscription_actual += sum(abs(txn.amount) for txn in matches)
        subscription_planned += _subscription_planned_amount_for_period(subscription, start_date, end_date, use_cash_timing=use_cash_timing)
        subscription_count += 1

    if subscription_planned or subscription_actual:
        rows.append(
            {
                "label": "Monthly Subscriptions",
                "planned": subscription_planned,
                "actual": subscription_actual,
                "diff": subscription_actual - subscription_planned,
                "source": "subscriptions",
                "source_id": None,
                "category_label": SUBSCRIPTION_CATEGORY,
                "count": subscription_count,
                "transaction_ids": subscription_transaction_ids,
            }
        )

    unplanned_fixed_transactions = [
        txn
        for txn in transactions
        if txn.id not in matched_transaction_ids and txn.category and txn.category.name in FIXED_EXPENSE_CATEGORY_NAMES
    ]
    unplanned_actual = sum(abs(txn.amount) for txn in unplanned_fixed_transactions)
    if unplanned_actual:
        rows.append(
            {
                "label": "Other Fixed Expenses",
                "planned": 0,
                "actual": unplanned_actual,
                "diff": unplanned_actual,
                "source": "other_fixed_expenses",
                "category_label": "Other",
                "transaction_ids": [txn.id for txn in unplanned_fixed_transactions],
            }
        )

    return _sort_plan_detail_rows(rows)


def variable_plan_detail_rows(db: Session, user: User, target_date: date | None = None, start_date: date | None = None, end_date: date | None = None) -> list[dict]:
    from app.services.subscription_service import active_subscription_rows

    if start_date and end_date:
        month_transactions = _expense_transactions_between(db, user, start_date, end_date)
        generated_entries = _generated_entries_between(db, user, _generate_variable_entries, start_date, end_date)
        planned_by_label = defaultdict(float)
        for entry in generated_entries:
            planned_by_label[entry["description"]] += entry["amount"]
        one_time_planned_by_label = _planned_entries_by_label(
            _generated_entries_between(db, user, _generate_one_time_entries, start_date, end_date),
            item_type="expense",
            source="one_time",
            unique_entries=True,
        )
    else:
        start_date, end_date = month_bounds(target_date)
        month_transactions = _month_expense_transactions(db, user, target_date)
        planned_by_label = None
        one_time_planned_by_label = _planned_entries_by_label(
            _generated_entries_between(db, user, _generate_one_time_entries, start_date, end_date),
            item_type="expense",
            source="one_time",
            unique_entries=True,
        )
    subscription_rows = active_subscription_rows(db, user, purpose="monthly_plan")
    fixed_claimed_transaction_ids = _fixed_plan_claimed_transaction_ids(
        db,
        user,
        month_transactions,
        subscription_rows=subscription_rows,
    )
    transactions = [
        txn
        for txn in month_transactions
        if txn.id not in fixed_claimed_transaction_ids
        and (txn.category.name if txn.category else "") not in FIXED_EXPENSE_CATEGORY_NAMES
        and not any(_transaction_matches_subscription(txn, row["subscription"]) for row in subscription_rows)
    ]
    rows = []
    matched_transaction_ids = set()

    for item in sorted(
        db.scalars(select(VariableExpenseItem).where(VariableExpenseItem.user_id == user.id)).all(),
        key=lambda expense: (expense.name or "").lower(),
    ):
        matches = [txn for txn in transactions if _transaction_matches_planned_item(txn, item.name)]
        matched_transaction_ids.update(txn.id for txn in matches)
        actual = sum(abs(txn.amount) for txn in matches)
        planned = planned_by_label[item.name] if planned_by_label is not None else monthly_amount_for_variable_item(item)
        if planned or actual:
            rows.append(
                {
                    "label": item.name,
                    "planned": planned,
                    "actual": actual,
                    "diff": actual - planned,
                    "source": "variable_expense",
                    "source_id": item.id,
                    "category_label": item.category_label or item.name,
                    "transaction_ids": [txn.id for txn in matches],
                }
            )

    _append_forecast_detail_rows(rows, transactions, matched_transaction_ids, one_time_planned_by_label)

    unplanned_variable_transactions = [txn for txn in transactions if txn.id not in matched_transaction_ids]
    unplanned_actual = sum(abs(txn.amount) for txn in unplanned_variable_transactions)
    if unplanned_actual:
        rows.append(
            {
                "label": "Other Variable Expenses",
                "planned": 0,
                "actual": unplanned_actual,
                "diff": unplanned_actual,
                "source": "other_variable_expenses",
                "category_label": "Other",
                "transaction_ids": [txn.id for txn in unplanned_variable_transactions],
            }
        )

    return _sort_plan_detail_rows(rows)


# --- Monthly plan and budget snapshots ---------------------------------------


def get_or_create_monthly_plan(db: Session, user: User, target_date: date | None = None) -> MonthlyPlan:
    target_date = (target_date or app_today()).replace(day=1)
    plan = db.scalar(select(MonthlyPlan).where(MonthlyPlan.user_id == user.id, MonthlyPlan.month == target_date))
    if plan:
        return plan

    profile = user.profile or OnboardingProfile()
    monthly_income = monthly_income_from_profile(profile)
    monthly_tax = calculate_tax_estimate(profile).monthly_total
    fixed_total = fixed_expense_total(db, user, target_date)
    planned_savings = planned_savings_contribution_for_user(db, user, profile)
    retirement_total = retirement_cash_flow_contribution(profile)
    loan_extra_total = selected_loan_extra_payment_total(db, user)
    safe_target = (
        monthly_income
        - monthly_tax
        - fixed_total
        - planned_savings
        - (profile.planned_debt_payment or 0)
        - retirement_total
        - loan_extra_total
    )
    plan = MonthlyPlan(
        user_id=user.id,
        month=target_date,
        income=monthly_income,
        fixed_expenses=fixed_total,
        planned_savings=planned_savings,
        planned_debt_payment=profile.planned_debt_payment or 0,
        safe_to_spend_target=safe_target,
    )
    db.add(plan)
    db.commit()
    return plan


def sync_monthly_plan(db: Session, user: User, target_date: date | None = None, *, purpose: str = "monthly_plan") -> MonthlyPlan:
    assert_plaid_data_purpose(purpose)
    plan = get_or_create_monthly_plan(db, user, target_date)
    profile = user.profile or OnboardingProfile()
    plan.income = monthly_income_from_profile(profile)
    monthly_tax = calculate_tax_estimate(profile).monthly_total
    retirement_total = retirement_cash_flow_contribution(profile)
    loan_extra_total = selected_loan_extra_payment_total(db, user)
    planned_savings = planned_savings_contribution_for_user(db, user, profile)
    plan.fixed_expenses = fixed_expense_total(db, user, target_date)
    plan.planned_savings = planned_savings
    plan.planned_debt_payment = profile.planned_debt_payment or 0
    plan.safe_to_spend_target = (
        plan.income - monthly_tax - plan.fixed_expenses - plan.planned_savings - plan.planned_debt_payment - retirement_total - loan_extra_total
    )
    db.commit()
    sync_monthly_budget_snapshot(db, user, target_date, purpose=purpose)
    return plan


def transaction_category_allocations_for_period(db: Session, user: User, start_date: date, end_date: date, *, purpose: str = "monthly_plan") -> list[dict]:
    assert_plaid_data_purpose(purpose)
    transactions = db.scalars(
        select(Transaction)
        .options(
            joinedload(Transaction.category),
            joinedload(Transaction.account),
            selectinload(Transaction.splits).joinedload(TransactionSplit.category),
        )
        .where(
            Transaction.user_id == user.id,
            Transaction.posted_date >= start_date,
            Transaction.posted_date <= end_date,
            Transaction.amount < 0,
        )
        .order_by(Transaction.posted_date.desc(), Transaction.id.desc())
    ).all()
    allocations = []
    for transaction in transactions:
        split_rows = [split for split in transaction.splits if (split.amount or 0) > 0]
        if split_rows:
            for split in split_rows:
                category = split.category
                if not category_counts_as_spending(category):
                    continue
                label = (category.name if category else "Other") or "Other"
                allocations.append(
                    {
                        "transaction": transaction,
                        "transaction_id": transaction.id,
                        "category": category,
                        "category_id": split.category_id,
                        "category_name": label,
                        "amount": abs(split.amount or 0),
                        "is_split": True,
                    }
                )
            continue

        category = transaction.category
        if not category_counts_as_spending(category):
            continue
        label = (category.name if category else "Other") or "Other"
        allocations.append(
            {
                "transaction": transaction,
                "transaction_id": transaction.id,
                "category": category,
                "category_id": transaction.category_id,
                "category_name": label,
                "amount": abs(transaction.amount or 0),
                "is_split": False,
            }
        )
    return allocations


def _month_income_total(db: Session, user: User, month_start: date) -> float:
    start, end = month_bounds(month_start)
    return float(sum(transaction.amount or 0 for transaction in _income_transactions_between(db, user, start, end)))


def _month_expense_total(db: Session, user: User, month_start: date) -> float:
    start, end = month_bounds(month_start)
    return float(sum(allocation["amount"] for allocation in transaction_category_allocations_for_period(db, user, start, end, purpose="monthly_plan")))


def _budget_group_key_for_snapshot(category: Category | None, label: str) -> str:
    saved_key = (getattr(category, "budget_group_key", None) or "").strip()
    group_keys = {group["key"] for group in STARTER_CATEGORY_GROUPS}
    if saved_key in group_keys:
        return saved_key

    normalized = (label or "").strip().lower()
    for group in STARTER_CATEGORY_GROUPS:
        if normalized in group["aliases"]:
            return group["key"]
    for group in STARTER_CATEGORY_GROUPS:
        if any(keyword in normalized for keyword in group["keywords"]):
            return group["key"]
    return "miscellaneous"


def _budget_category_snapshot_rows(db: Session, user: User, month_start: date, *, purpose: str = "monthly_plan") -> list[dict]:
    start, end = month_bounds(month_start)
    transactions_by_category = defaultdict(list)
    categories_by_key: dict[str, Category] = {}
    income_transactions = _income_transactions_between(db, user, start, end)
    actual_income_total = float(sum(transaction.amount or 0 for transaction in income_transactions))

    user_categories = db.scalars(select(Category).where(Category.user_id == user.id)).all()
    for category in user_categories:
        categories_by_key[category.name.strip().lower()] = category

    for allocation in transaction_category_allocations_for_period(db, user, start, end, purpose=purpose):
        label = (allocation["category_name"] or "Other").strip() or "Other"
        key = label.lower()
        transactions_by_category[key].append(allocation)
        category = allocation.get("category")
        if category and key not in categories_by_key:
            categories_by_key[key] = category

    rows = []
    active_budget_keys = {
        key
        for key, category in categories_by_key.items()
        if category_is_active_budget(db, category, user)
    }
    cleanup_allocations = [
        allocation
        for key, allocations in transactions_by_category.items()
        if key not in active_budget_keys
        for allocation in allocations
    ]
    for normalized_label in sorted(active_budget_keys):
        category = categories_by_key.get(normalized_label)
        allocations = transactions_by_category.get(normalized_label, [])
        label = category.name if category else ((allocations[0]["category_name"] if allocations else "Other") or "Other")
        category_kind = category.kind if category else "expense"
        if category and category_kind not in {"expense", "income"}:
            continue
        if category_kind == "income" and normalize_text(label) != "income":
            continue
        if category and category.user_id == user.id and category.is_default and not allocations and category_kind != "income":
            continue

        planned = max(category.monthly_target if category else 0, 0)
        actual = sum(allocation["amount"] for allocation in allocations)
        transaction_ids = sorted({int(allocation["transaction_id"]) for allocation in allocations if allocation.get("transaction_id")})
        if category_kind == "income":
            planned = max(planned, monthly_income_from_profile(user.profile))
            actual = actual_income_total if actual_income_total > 0 else planned
            transaction_ids = sorted(transaction.id for transaction in income_transactions)
        if planned <= 0 and actual <= 0 and not transaction_ids:
            continue

        rows.append(
            {
                "category_id": category.id if category else None,
                "category_name": label,
                "category_kind": category_kind,
                "planned": float(planned or 0),
                "actual": float(actual or 0),
                "group_key": _budget_group_key_for_snapshot(category, label),
                "sort_order": category.budget_sort_order if category else None,
                "transaction_count": len(transaction_ids),
                "transaction_ids_json": json.dumps(transaction_ids),
            }
        )
    if cleanup_allocations:
        transaction_ids = sorted({int(allocation["transaction_id"]) for allocation in cleanup_allocations if allocation.get("transaction_id")})
        actual = sum(allocation["amount"] for allocation in cleanup_allocations)
        rows.append(
            {
                "category_id": None,
                "category_name": "Other Spending To Categorize",
                "category_kind": "cleanup",
                "planned": 0.0,
                "actual": float(actual or 0),
                "group_key": "miscellaneous",
                "sort_order": None,
                "transaction_count": len(transaction_ids),
                "transaction_ids_json": json.dumps(transaction_ids),
            }
        )
    return rows


def sync_monthly_budget_category_snapshots(db: Session, user: User, target_date: date | None = None, *, purpose: str = "monthly_plan", force: bool = False) -> list[MonthlyBudgetCategorySnapshot]:
    assert_plaid_data_purpose(purpose)
    month_start = (target_date or app_today()).replace(day=1)
    current_month_start = app_today().replace(day=1)
    existing_rows = db.scalars(
        select(MonthlyBudgetCategorySnapshot).where(
            MonthlyBudgetCategorySnapshot.user_id == user.id, MonthlyBudgetCategorySnapshot.month == month_start
        )
    ).all()
    if existing_rows and month_start < current_month_start and not force:
        return existing_rows

    if existing_rows:
        for row in existing_rows:
            db.delete(row)
        db.flush()

    snapshots = []
    for row in _budget_category_snapshot_rows(db, user, month_start, purpose=purpose):
        snapshot_row = MonthlyBudgetCategorySnapshot(user_id=user.id, month=month_start, **row)
        db.add(snapshot_row)
        snapshots.append(snapshot_row)
    return snapshots


def monthly_budget_category_snapshots_for_user(db: Session, user: User, target_date: date | None = None, *, purpose: str = "monthly_plan") -> list[MonthlyBudgetCategorySnapshot]:
    assert_plaid_data_purpose(purpose)
    month_start = (target_date or app_today()).replace(day=1)
    rows = db.scalars(
        select(MonthlyBudgetCategorySnapshot)
        .where(MonthlyBudgetCategorySnapshot.user_id == user.id, MonthlyBudgetCategorySnapshot.month == month_start)
        .order_by(
            MonthlyBudgetCategorySnapshot.sort_order.is_(None),
            MonthlyBudgetCategorySnapshot.sort_order.asc(),
            MonthlyBudgetCategorySnapshot.category_name.asc(),
        )
    ).all()
    if rows:
        return rows

    rows = sync_monthly_budget_category_snapshots(db, user, month_start, purpose=purpose)
    db.commit()
    return rows


def sync_monthly_budget_snapshot(db: Session, user: User, target_date: date | None = None, *, purpose: str = "monthly_plan") -> MonthlyBudgetSnapshot:
    assert_plaid_data_purpose(purpose)
    month_start = (target_date or app_today()).replace(day=1)
    snapshot = db.scalar(
        select(MonthlyBudgetSnapshot).where(MonthlyBudgetSnapshot.user_id == user.id, MonthlyBudgetSnapshot.month == month_start)
    )
    if not snapshot:
        snapshot = MonthlyBudgetSnapshot(user_id=user.id, month=month_start)
        db.add(snapshot)

    plan = get_or_create_monthly_plan(db, user, month_start)
    profile = user.profile or OnboardingProfile()
    tax_total = calculate_tax_estimate(profile).monthly_total
    retirement_total = retirement_cash_flow_contribution(profile)
    loan_extra_total = selected_loan_extra_payment_total(db, user)
    variable_plan_total = variable_expense_plan_total(db, user)
    fixed_details = fixed_plan_detail_rows(db, user, target_date=month_start)
    variable_details = variable_plan_detail_rows(db, user, target_date=month_start)
    actual_income = _month_income_total(db, user, month_start)
    actual_fixed = sum(row["actual"] for row in fixed_details)
    actual_variable = sum(row["actual"] for row in variable_details)
    actual_total_expenses = _month_expense_total(db, user, month_start)
    expected_cash_flow = (
        plan.income
        - tax_total
        - plan.fixed_expenses
        - variable_plan_total
        - plan.planned_savings
        - plan.planned_debt_payment
        - retirement_total
        - loan_extra_total
    )
    budget_remaining = (plan.fixed_expenses + variable_plan_total + tax_total) - (actual_fixed + actual_variable)

    snapshot.planned_income = plan.income
    snapshot.planned_fixed_expenses = plan.fixed_expenses
    snapshot.planned_variable_expenses = variable_plan_total
    snapshot.planned_savings = plan.planned_savings
    snapshot.planned_debt_payment = plan.planned_debt_payment + loan_extra_total
    snapshot.planned_taxes = tax_total
    snapshot.planned_retirement = retirement_total
    snapshot.planned_safe_to_spend = plan.safe_to_spend_target
    snapshot.expected_cash_flow = expected_cash_flow
    snapshot.budget_remaining = budget_remaining
    snapshot.actual_income = actual_income
    snapshot.actual_fixed_expenses = actual_fixed
    snapshot.actual_variable_expenses = actual_variable
    snapshot.actual_total_expenses = actual_total_expenses
    snapshot.net_cash_flow = actual_income - actual_total_expenses
    sync_monthly_budget_category_snapshots(db, user, month_start, purpose=purpose)
    db.commit()
    return snapshot


def analytics_months(end_month: date | None = None, range_key: str = "month") -> list[date]:
    if range_key not in ANALYTICS_RANGE_OPTIONS:
        range_key = "month"
    month_count = {"month": 1, "quarter": 3, "six_months": 6, "year": 12}[range_key]
    end_month = (end_month or app_today()).replace(day=1)
    start_month = add_months(end_month, -(month_count - 1))
    months = []
    cursor = start_month
    while cursor <= end_month:
        months.append(cursor)
        cursor = add_months(cursor, 1)
    return months


def parse_month_input(raw_value: str | None) -> date:
    if not raw_value:
        return app_today().replace(day=1)
    return datetime.strptime(f"{raw_value}-01", "%Y-%m-%d").date()


def sync_monthly_budget_snapshots_for_range(db: Session, user: User, months: list[date], *, purpose: str = "monthly_plan") -> list[MonthlyBudgetSnapshot]:
    assert_plaid_data_purpose(purpose)
    return [sync_monthly_budget_snapshot(db, user, month, purpose=purpose) for month in months]


def spending_by_category_between(db: Session, user: User, start_date: date, end_date: date, limit: int = 8, *, purpose: str = "monthly_plan") -> list[dict]:
    assert_plaid_data_purpose(purpose)
    totals: dict[str, dict] = defaultdict(lambda: {"amount": 0.0, "category_id": None})
    for allocation in transaction_category_allocations_for_period(db, user, start_date, end_date, purpose=purpose):
        row = totals[allocation["category_name"]]
        row["amount"] += allocation["amount"]
        row["category_id"] = row["category_id"] or allocation.get("category_id")
    rows = sorted(totals.items(), key=lambda row: row[1]["amount"], reverse=True)[:limit]
    return [
        {"category": category, "category_id": row["category_id"], "amount": float(row["amount"] or 0)}
        for category, row in rows
    ]


# Budget-row helpers ported from Flask main.py at cb7d969 (incl. 964c369
# budgets-from-transaction-categories).

BUDGET_CATEGORY_GROUP_BY_KEY = {group["key"]: group for group in STARTER_CATEGORY_GROUPS}


def current_budget_month_start() -> date:
    return app_today().replace(day=1)


def budget_category_group_for_label(label: str) -> dict:
    normalized = (label or "").strip().lower()
    for group in STARTER_CATEGORY_GROUPS:
        if normalized in group["aliases"]:
            return group
    for group in STARTER_CATEGORY_GROUPS:
        if any(keyword in normalized for keyword in group["keywords"]):
            return group
    return BUDGET_CATEGORY_GROUP_BY_KEY["miscellaneous"]


def budget_category_group_for_row(category: Category | None, label: str) -> dict:
    saved_key = (category.budget_group_key if category else "") or ""
    if saved_key in BUDGET_CATEGORY_GROUP_BY_KEY:
        return BUDGET_CATEGORY_GROUP_BY_KEY[saved_key]
    return budget_category_group_for_label(label)


def budget_row_is_canonical_income(label: str) -> bool:
    return normalize_text(label) == "income"


def editable_budget_category_for_user(db: Session, category: Category, user: User) -> Category:
    if category.user_id == user.id:
        return category

    existing = db.scalar(
        select(Category).where(
            Category.user_id == user.id,
            func.lower(Category.name) == category.name.strip().lower(),
        )
    )
    if existing:
        return existing

    override = Category(
        user_id=user.id,
        name=category.name,
        kind=category.kind,
        monthly_target=category.monthly_target,
        is_default=False,
    )
    db.add(override)
    return override


def active_budget_categories_by_key(db: Session, user: User) -> dict[str, Category]:
    planning_labels = {
        normalize_text(getattr(item, "category_label", "") or "")
        for item in [
            *db.scalars(select(FixedExpenseItem).where(FixedExpenseItem.user_id == user.id)).all(),
            *db.scalars(select(VariableExpenseItem).where(VariableExpenseItem.user_id == user.id)).all(),
            *db.scalars(select(ForecastItem).where(ForecastItem.user_id == user.id, ForecastItem.item_type == "expense")).all(),
            *db.scalars(select(RecurringForecastTemplate).where(RecurringForecastTemplate.user_id == user.id, RecurringForecastTemplate.item_type == "expense")).all(),
        ]
        if normalize_text(getattr(item, "category_label", "") or "")
    }
    return {
        normalize_text(category.name): category
        for category in categories_for_user(db, user)
        if category_is_active_budget(db, category, user, planning_labels=planning_labels)
    }


def initial_budget_target_for_transaction_category(db: Session, category: Category, user: User, transaction: Transaction | None = None) -> float:
    month_start = current_budget_month_start()
    month_end = month_start.replace(day=calendar.monthrange(month_start.year, month_start.month)[1])
    category_key = normalize_text(category.name or "")
    current_month_actual = sum(
        allocation["amount"]
        for allocation in transaction_category_allocations_for_period(db, user, month_start, month_end, purpose="monthly_plan")
        if normalize_text(allocation.get("category_name") or "") == category_key
    )
    transaction_actual = abs(transaction.amount or 0) if transaction and (transaction.amount or 0) < 0 else 0
    actual_basis = current_month_actual or transaction_actual
    rounded_actual = math.ceil(actual_basis / 25) * 25 if actual_basis > 0 else 0
    return max(DEFAULT_CATEGORY_TARGETS.get(category.name, 0), rounded_actual, 25)


def category_can_be_transaction_budget(category: Category | None) -> bool:
    if not category:
        return False
    return (category.kind or "expense") == "expense" and normalize_text(category.name or "") != "other"


def activate_transaction_budget_category(db: Session, category: Category, user: User, transaction: Transaction | None = None) -> tuple[Category, float]:
    editable_category = editable_budget_category_for_user(db, category, user)
    target = initial_budget_target_for_transaction_category(db, category, user, transaction)
    editable_category.kind = "expense"
    editable_category.monthly_target = target
    editable_category.is_default = False
    return editable_category, target


def transaction_budget_action(db: Session, transaction: Transaction, user: User, active_budget_keys: set[str] | None = None) -> dict | None:
    category = transaction.category
    if (transaction.amount or 0) >= 0 or not category_can_be_transaction_budget(category):
        return None
    if active_budget_keys is None:
        active_budget_keys = set(active_budget_categories_by_key(db, user))
    if normalize_text(category.name or "") in active_budget_keys:
        return None
    target = initial_budget_target_for_transaction_category(db, category, user, transaction)
    return {
        "category_name": category.name,
        "target": target,
        "target_label": f"${target:,.0f}",
        "hint": f"Starts {category.name} at ${target:,.0f} per month.",
    }


def sync_loan_fixed_expense_budget(db: Session, item: FixedExpenseItem, user: User, *, force: bool = False) -> Category | None:
    if force:
        item.is_loan = True
    if not (force or loan_category_for_item(item)):
        return None
    category = ensure_category_option(db, item.category_label or item.name, user)
    if not category:
        return None
    editable_category = editable_budget_category_for_user(db, category, user)
    category_key = normalize_text(editable_category.name)
    loan_items = [
        candidate
        for candidate in db.scalars(select(FixedExpenseItem).where(FixedExpenseItem.user_id == user.id)).all()
        if (candidate.is_loan or loan_category_for_item(candidate)) and normalize_text(candidate.category_label or candidate.name) == category_key
    ]
    loan_plans = {plan.fixed_expense_item_id: plan for plan in db.scalars(select(LoanPlan).where(LoanPlan.user_id == user.id)).all()}
    scheduled_loan_total = sum(monthly_amount_for_fixed_item(candidate) for candidate in loan_items)
    selected_extra_total = sum(selected_extra_payment_for_loan_plan(loan_plans.get(candidate.id)) for candidate in loan_items)
    possible_extra_totals = {0.0}
    for candidate in loan_items:
        plan = loan_plans.get(candidate.id)
        options = {0.0}
        if plan:
            options.add(max(plan.extra_payment_one or 0, 0))
            options.add(max(plan.extra_payment_two or 0, 0))
        possible_extra_totals = {
            round(existing + option, 2)
            for existing in possible_extra_totals
            for option in options
        }
    possible_auto_targets = {
        round(scheduled_loan_total + extra_total, 2)
        for extra_total in possible_extra_totals
    }
    monthly_payment = max(monthly_amount_for_fixed_item(item), 0)
    target = max(monthly_payment, scheduled_loan_total + selected_extra_total, 0)
    current_target = round(editable_category.monthly_target or 0, 2)
    if target > editable_category.monthly_target or editable_category.is_default or current_target in possible_auto_targets:
        editable_category.monthly_target = target
    editable_category.is_default = False
    return editable_category


def sync_planning_item_budget_target(db: Session, category_label: str | None, user: User) -> Category | None:
    category_label = (category_label or "").strip() or "Other"
    category = ensure_category_option(db, category_label, user)
    if not category or category.kind != "expense":
        return None
    category_key = normalize_text(category.name)
    scheduled_total = 0.0
    for item in db.scalars(select(FixedExpenseItem).where(FixedExpenseItem.user_id == user.id)).all():
        if normalize_text(item.category_label or "Other") == category_key:
            scheduled_total += monthly_amount_for_fixed_item(item)
    for item in db.scalars(select(VariableExpenseItem).where(VariableExpenseItem.user_id == user.id)).all():
        if normalize_text(item.category_label or "Other") == category_key:
            scheduled_total += monthly_amount_for_variable_item(item)
    for template in db.scalars(select(RecurringForecastTemplate).where(RecurringForecastTemplate.user_id == user.id, RecurringForecastTemplate.item_type == "expense")).all():
        if normalize_text(template.category_label or "Other") == category_key:
            scheduled_total += recurring_template_monthly_amount(template)
    if scheduled_total <= 0:
        return None
    editable_category = editable_budget_category_for_user(db, category, user)
    editable_category.monthly_target = round(scheduled_total, 2)
    editable_category.is_default = False
    return editable_category


def amount_for_monthly_target(monthly_target: float, frequency: str | None, occurrence_multiplier: int = 1) -> float:
    occurrence_multiplier = max(int(occurrence_multiplier or 1), 1)
    monthly_target = max(monthly_target or 0, 0) / occurrence_multiplier
    frequency = frequency or "monthly"
    if frequency == "annual":
        return monthly_target * 12
    if frequency == "quarterly":
        return monthly_target * 3
    if frequency == "semimonthly":
        return monthly_target / 2
    if frequency == "biweekly":
        return monthly_target * 12 / 26
    if frequency == "weekly":
        return monthly_target * 12 / 52
    return monthly_target


def planning_item_occurrence_multiplier(item) -> int:
    frequency = getattr(item, "frequency", None)
    if frequency not in {"weekly", "biweekly"}:
        return 1
    days_of_week = getattr(item, "days_of_week", None)
    if hasattr(item, "use_specific_date") and not item.use_specific_date:
        return 1
    return max(len(weekday_values(days_of_week)), 1)


def recurring_template_monthly_amount(template: RecurringForecastTemplate) -> float:
    return monthly_amount_for_frequency(template.amount or 0, template.frequency or "monthly") * planning_item_occurrence_multiplier(template)


def recorded_month_income(db: Session, user: User, target_date: date | None = None) -> float:
    # The monthly-plan page's metrics.month_income: recorded income for the
    # month, falling back to the planned income when nothing is recorded yet.
    return _month_income_total(db, user, target_date or app_today())


def budget_anchor_for_label(label: str | None) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (label or "other").lower()).strip("-")
    return f"budget-{slug or 'other'}"


def budget_category_match_terms(label: str) -> set[str]:
    normalized = normalize_text(label)
    terms = {normalized}
    terms.update(term for term in re.split(r"[^a-z0-9]+", normalized) if len(term) >= 4)
    terms.update(BUDGET_CATEGORY_TRANSACTION_HINTS.get(normalized, ()))
    return {normalize_text(term) for term in terms if normalize_text(term)}


def budget_suggestion_candidate(transaction: Transaction) -> bool:
    category_name = normalize_text(transaction.category.name if transaction.category else "")
    return not category_name or category_name == "other"


def transaction_matches_budget_category(transaction: Transaction, label: str) -> bool:
    haystack = normalize_text(" ".join([transaction.description or "", transaction.merchant or "", transaction.source_name or ""]))
    if not haystack:
        return False
    return any(term in haystack for term in budget_category_match_terms(label))


def tax_plan_detail_rows(tax_estimate: TaxEstimate, multiplier: float = 1.0) -> list[dict]:
    payroll_tax = (tax_estimate.social_security_tax + tax_estimate.medicare_tax + tax_estimate.additional_medicare_tax) / 12 * multiplier
    rows = [
        {
            "label": "Federal Income Tax",
            "planned": tax_estimate.federal_income_tax / 12 * multiplier,
            "actual": 0,
            "source": "tax",
            "table_target": "tax-table-federal",
        },
        {
            "label": "State Income Tax",
            "planned": tax_estimate.state_income_tax / 12 * multiplier,
            "actual": 0,
            "source": "tax",
            "table_target": "tax-table-state",
        },
        {
            "label": "Social Security And Medicare Taxes",
            "planned": payroll_tax,
            "actual": 0,
            "source": "tax",
            "table_target": "tax-table-payroll",
        },
    ]
    if tax_estimate.additional_tax_monthly:
        rows.append(
            {
                "label": tax_estimate.additional_tax_label,
                "planned": tax_estimate.additional_tax_monthly * multiplier,
                "actual": 0,
                "source": "tax",
                "table_target": "tax-table-additional",
            }
        )
    for row in rows:
        row["diff"] = row["actual"] - row["planned"]
    return rows


def spending_by_category(db: Session, user: User, target_date: date | None = None, *, purpose: str = "dashboard") -> list[dict]:
    assert_plaid_data_purpose(purpose)
    target_date = target_date or app_today()
    start, end = month_bounds(target_date)
    totals: dict[str, dict] = defaultdict(lambda: {"amount": 0.0, "category_id": None})
    for allocation in transaction_category_allocations_for_period(db, user, start, end, purpose=purpose):
        row = totals[allocation["category_name"]]
        row["amount"] += allocation["amount"]
        row["category_id"] = row["category_id"] or allocation.get("category_id")
    rows = sorted(totals.items(), key=lambda row: row[1]["amount"], reverse=True)[:6]
    return [
        {"category": category, "category_id": row["category_id"], "amount": float(row["amount"] or 0)}
        for category, row in rows
    ]


# Recurring-templates-from-transactions cluster ported from Flask main.py at
# cb7d969 (0ddefb0 "Add recurring expense planning from transactions").


def _template_note_has_transaction(template: RecurringForecastTemplate, transaction: Transaction) -> bool:
    if not transaction.id:
        return False
    return bool(re.search(rf"\btransaction #{transaction.id}\b", template.notes or "", re.IGNORECASE))


def _append_recurring_transaction_note(template: RecurringForecastTemplate, transaction: Transaction) -> None:
    if not transaction.id:
        return
    date_text = transaction.posted_date.isoformat() if transaction.posted_date else "date not set"
    marker = f"transaction #{transaction.id}"
    notes = template.notes or ""
    if marker not in notes.lower():
        template.notes = f"{notes} Created from transaction #{transaction.id} dated {date_text}.".strip()


def _recurring_template_matches_transaction(
    template: RecurringForecastTemplate,
    transaction: Transaction,
    category: Category,
    proposed_name: str,
    amount: float,
) -> bool:
    if template.item_type != "expense":
        return False
    if _template_note_has_transaction(template, transaction):
        return True

    template_category = normalize_text(template.category_label or "")
    transaction_category = normalize_text(category.name if category else "")
    if template_category and transaction_category and template_category != transaction_category:
        return False

    template_amount = abs(template.amount or 0)
    amount_exact = abs(template_amount - amount) < 0.01
    amount_close = abs(template_amount - amount) <= max(2.0, amount * 0.1)
    if not (amount_exact or amount_close):
        return False

    template_text = normalize_text(template.name or "")
    transaction_texts = [
        normalize_text(proposed_name),
        normalize_text(transaction.merchant or ""),
        normalize_text(transaction.description or ""),
    ]
    return any(
        template_text
        and text
        and (template_text in text or text in template_text)
        for text in transaction_texts
    )


def _recurring_template_candidates_for_transaction(db: Session, transaction: Transaction, category: Category, name: str, amount: float) -> list[RecurringForecastTemplate]:
    candidates = []
    for template in db.scalars(select(RecurringForecastTemplate).where(RecurringForecastTemplate.user_id == transaction.user_id, RecurringForecastTemplate.item_type == "expense")).all():
        if _recurring_template_matches_transaction(template, transaction, category, name, amount):
            candidates.append(template)
    return sorted(
        candidates,
        key=lambda template: (
            0 if _template_note_has_transaction(template, transaction) else 1,
            template.id or 0,
        ),
    )


def _merge_recurring_template_notes(primary: RecurringForecastTemplate, duplicate: RecurringForecastTemplate) -> None:
    primary_notes = primary.notes or ""
    for transaction_id in re.findall(r"transaction #(\d+)", duplicate.notes or "", re.IGNORECASE):
        marker = f"transaction #{transaction_id}"
        if marker not in primary_notes.lower():
            primary_notes = f"{primary_notes} Created from transaction #{transaction_id}.".strip()
    primary.notes = primary_notes or primary.notes


def _apply_transaction_recurring_schedule(
    template: RecurringForecastTemplate,
    transaction: Transaction,
    category: Category,
    *,
    name: str,
    amount: float,
    frequency: str,
    start_date: date,
    second_date: date | None,
    selected_weekdays: list[str],
    monthly_week_numbers: str | None,
    monthly_weekday: int | None,
) -> None:
    template.name = name[:160]
    template.amount = amount
    template.item_type = "expense"
    template.frequency = frequency
    template.start_date = start_date
    template.second_date = second_date
    template.days_of_week = ",".join(selected_weekdays) if selected_weekdays else None
    template.second_day_of_month = second_date.day if second_date else None
    template.monthly_week_numbers = monthly_week_numbers
    template.monthly_weekday = monthly_weekday
    template.category_label = category.name
    _append_recurring_transaction_note(template, transaction)


def recurring_monthly_week_pattern(selected_week_numbers: list[str | int] | None, monthly_weekday_raw: str | int | None) -> tuple[str | None, int | None]:
    selected_weeks = [
        str(value)
        for value in (selected_week_numbers or [])
        if str(value) in {str(week) for week in MONTHLY_WEEK_OPTIONS}
    ]
    try:
        monthly_weekday = int(monthly_weekday_raw if monthly_weekday_raw is not None else "")
    except (TypeError, ValueError):
        monthly_weekday = None
    if monthly_weekday not in WEEKDAY_OPTIONS or not selected_weeks:
        return None, None
    return ",".join(selected_weeks), monthly_weekday


def create_recurring_template_from_transaction(
    db: Session,
    user: User,
    transaction: Transaction,
    category: Category,
    *,
    recurring_name: str | None = None,
    recurring_start_date: str | None = None,
    recurring_second_date: str | None = None,
    recurring_frequency: str = "monthly",
    recurring_days_of_week: list[str | int] | None = None,
    recurring_monthly_week_numbers: list[str | int] | None = None,
    recurring_monthly_weekday: str | int | None = None,
) -> tuple[str, bool]:
    from app.services.transaction_service import parse_flexible_date

    if transaction.amount >= 0:
        return "Category updated. Recurring schedules from Transactions are for expense charges; income belongs in Income Planning.", False

    raw_start = (recurring_start_date or "").strip()
    raw_second_date = (recurring_second_date or "").strip()
    frequency = recurring_frequency or "monthly"
    selected_weekdays = [
        str(value)
        for value in (recurring_days_of_week or [])
        if str(value) in {str(day) for day in WEEKDAY_OPTIONS}
    ]
    monthly_week_numbers, monthly_weekday = recurring_monthly_week_pattern(recurring_monthly_week_numbers, recurring_monthly_weekday)
    name = (recurring_name or transaction.merchant or transaction.description or "Recurring expense").strip()
    amount = abs(transaction.amount or 0)

    try:
        start_date = parse_flexible_date(raw_start) if raw_start else transaction.posted_date
    except ValueError:
        start_date = None
    try:
        second_date = parse_flexible_date(raw_second_date) if raw_second_date else None
    except ValueError:
        second_date = None

    if frequency not in RECURRING_FREQUENCY_OPTIONS:
        return "Category updated, but the recurring cadence was not valid.", False
    if not start_date:
        return "Category updated, but the recurring start date was not valid.", False
    if frequency == "semimonthly" and raw_second_date and not second_date:
        return "Category updated, but the second recurring date was not valid.", False
    if frequency in {"weekly", "biweekly"} and not selected_weekdays:
        selected_weekdays = [str(start_date.weekday())]

    category_label = category.name
    matching_templates = _recurring_template_candidates_for_transaction(db, transaction, category, name, amount)
    if matching_templates:
        primary_template = matching_templates[0]
        for duplicate_template in matching_templates[1:]:
            _merge_recurring_template_notes(primary_template, duplicate_template)
            db.delete(duplicate_template)
        _apply_transaction_recurring_schedule(
            primary_template,
            transaction,
            category,
            name=name,
            amount=amount,
            frequency=frequency,
            start_date=start_date,
            second_date=second_date,
            selected_weekdays=selected_weekdays,
            monthly_week_numbers=monthly_week_numbers,
            monthly_weekday=monthly_weekday,
        )
        return "Category updated and recurring expense schedule updated for matching transactions.", True

    template = RecurringForecastTemplate(
        user_id=user.id,
        name=name[:160],
        amount=amount,
        item_type="expense",
        frequency=frequency,
        start_date=start_date,
        second_date=second_date,
        days_of_week=",".join(selected_weekdays) if selected_weekdays else None,
        second_day_of_month=second_date.day if second_date else None,
        monthly_week_numbers=monthly_week_numbers,
        monthly_weekday=monthly_weekday,
        category_label=category_label,
    )
    _append_recurring_transaction_note(template, transaction)
    db.add(template)
    return "Category updated and recurring expense schedule added to forecasts and cash balance projections.", True


def recurring_transaction_ids_for_page(db: Session, user: User, transactions: list[Transaction]) -> set[int]:
    transaction_by_id = {transaction.id: transaction for transaction in transactions if transaction.id}
    if not transaction_by_id:
        return set()

    recurring_ids: set[int] = set()
    templates = db.scalars(select(RecurringForecastTemplate).where(RecurringForecastTemplate.user_id == user.id, RecurringForecastTemplate.item_type == "expense")).all()
    for template in templates:
        notes = template.notes or ""
        for raw_id in re.findall(r"transaction #(\d+)", notes, re.IGNORECASE):
            transaction_id = int(raw_id)
            if transaction_id in transaction_by_id:
                recurring_ids.add(transaction_id)

    for transaction in transaction_by_id.values():
        if transaction.id in recurring_ids or (transaction.amount or 0) >= 0:
            continue
        transaction_category = (transaction.category.name if transaction.category else "") or ""
        transaction_text = normalize_text(transaction.merchant or transaction.description or "")
        transaction_amount = abs(transaction.amount or 0)
        for template in templates:
            if abs((template.amount or 0) - transaction_amount) >= 0.01:
                continue
            if template.category_label and transaction_category and normalize_text(template.category_label) != normalize_text(transaction_category):
                continue
            template_text = normalize_text(template.name or "")
            if template_text and transaction_text and (template_text in transaction_text or transaction_text in template_text):
                recurring_ids.add(transaction.id)
                break

    return recurring_ids


# Timing helpers ported from Flask main.py at cb7d969. Flask reads these
# straight from request.form; the API passes the raw values explicitly.


def next_date_for_selected_weekdays(selected_weekdays: list[str], anchor_date: date | None = None) -> date | None:
    weekdays = sorted(
        int(value)
        for value in selected_weekdays
        if value.isdigit() and int(value) in WEEKDAY_OPTIONS
    )
    if not weekdays:
        return None
    anchor = anchor_date or app_today()
    return min(anchor + timedelta(days=(weekday - anchor.weekday()) % 7) for weekday in weekdays)


def clean_selected_weekdays(raw_values: list[str | int] | None) -> list[str]:
    return [
        str(value)
        for value in (raw_values or [])
        if str(value).isdigit() and int(value) in WEEKDAY_OPTIONS
    ]


def fixed_expense_timing_from_values(
    frequency: str,
    start_date: date | None,
    second_date: date | None,
    selected_weekdays: list[str],
    selected_week_numbers: list[str | int] | None = None,
    monthly_weekday_raw: str | int | None = None,
) -> tuple[date | None, date | None, list[str], str | None, int | None]:
    selected_weeks = [
        str(value)
        for value in (selected_week_numbers or [])
        if str(value) in {str(week) for week in MONTHLY_WEEK_OPTIONS}
    ]
    try:
        monthly_weekday = int(monthly_weekday_raw if monthly_weekday_raw is not None else "")
    except (TypeError, ValueError):
        monthly_weekday = None
    if monthly_weekday not in WEEKDAY_OPTIONS:
        monthly_weekday = None
    monthly_week_numbers = ",".join(selected_weeks) if selected_weeks else None
    uses_weekday_pattern = monthly_weekday is not None
    if uses_weekday_pattern:
        if frequency in {"weekly", "biweekly"}:
            if not selected_weekdays:
                selected_weekdays = [str(monthly_weekday)]
            monthly_week_numbers = None
        elif frequency == "semimonthly":
            second_date = None
        elif frequency == "monthly":
            second_date = None
        else:
            monthly_week_numbers = None
            monthly_weekday = None
    else:
        monthly_week_numbers = None
        monthly_weekday = None

    if not start_date and frequency in {"weekly", "biweekly"} and selected_weekdays:
        start_date = next_date_for_selected_weekdays(selected_weekdays)
    if start_date and frequency in {"weekly", "biweekly"} and not selected_weekdays:
        selected_weekdays = [str(start_date.weekday())]
    return start_date, second_date, selected_weekdays, monthly_week_numbers, monthly_weekday


def paycheck_timing_values(
    cadence: str,
    next_pay_date: date | None,
    second_date: date | None,
    selected_weekdays: list[str | int] | None = None,
    selected_week_numbers: list[str | int] | None = None,
    monthly_weekday_raw: str | int | None = None,
) -> dict:
    cleaned_weekdays = clean_selected_weekdays(selected_weekdays)
    next_pay_date, second_date, cleaned_weekdays, monthly_week_numbers, monthly_weekday = fixed_expense_timing_from_values(
        cadence,
        next_pay_date,
        second_date,
        cleaned_weekdays,
        selected_week_numbers,
        monthly_weekday_raw,
    )
    timing_values = {
        "next_pay_date": next_pay_date,
        "paycheck_second_date": None,
        "paycheck_days_of_week": None,
        "paycheck_second_day_of_month": None,
        "paycheck_monthly_week_numbers": None,
        "paycheck_monthly_weekday": None,
    }
    if cadence in {"weekly", "biweekly"}:
        timing_values["paycheck_days_of_week"] = ",".join(cleaned_weekdays) if cleaned_weekdays else None
    elif cadence in {"monthly", "semimonthly"}:
        if cadence == "semimonthly":
            timing_values["paycheck_second_date"] = second_date
            timing_values["paycheck_second_day_of_month"] = second_date.day if second_date else None
        timing_values["paycheck_monthly_week_numbers"] = monthly_week_numbers
        timing_values["paycheck_monthly_weekday"] = monthly_weekday
    return timing_values


def _plaid_post_sync_hook(db: Session, user: User) -> None:
    sync_monthly_plan(db, user, purpose="monthly_plan")


# Flask calls sync_monthly_plan after subscription rescans on Plaid syncs.
# Import subscription_service before registering this hook so its hook always
# registers first — matching Flask's scan-then-sync ordering regardless of
# which router module is imported first at app startup.
from app.services import subscription_service as _subscription_service  # noqa: E402,F401

if _plaid_post_sync_hook not in plaid_service.POST_SYNC_HOOKS:
    plaid_service.POST_SYNC_HOOKS.append(_plaid_post_sync_hook)
