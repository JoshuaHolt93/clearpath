from __future__ import annotations

import calendar
import os
from dataclasses import dataclass
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.planning_constants import (
    ADDITIONAL_MEDICARE_RATE,
    ADDITIONAL_MEDICARE_THRESHOLDS,
    DEFAULT_APP_TIMEZONE,
    FEDERAL_TAX_BRACKETS_2026,
    MEDICARE_RATE_2026,
    MONTHLY_WEEK_OPTIONS,
    SOCIAL_SECURITY_RATE_2026,
    SOCIAL_SECURITY_WAGE_BASE_2026,
    STANDARD_DEDUCTIONS_2026,
    STATE_TAX_RULES_2026,
    TAX_FILING_STATUS_OPTIONS,
    WEEKDAY_OPTIONS,
)
from app.models import FixedExpenseItem, Goal, LoanPlan, OnboardingProfile, User, VariableExpenseItem

# Faithful port of the planning foundations from Flask services.py at 9b5dff0:
# timezone/date helpers, income normalization, retirement and loan-extra
# contributions, savings targets, and the 2026 tax estimation engine. The
# worksheet occurrence engine, monthly plan sync, and snapshots build on these
# in the next part of Phase 3.


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


@dataclass
class TaxEstimate:
    annual_gross_income: float
    taxable_income: float
    federal_income_tax: float
    state_income_tax: float
    social_security_tax: float
    medicare_tax: float
    additional_medicare_tax: float
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
    annual_total = federal_income_tax + state_income_tax + social_security_tax + medicare_tax + additional_medicare_tax
    return TaxEstimate(
        annual_gross_income=annual_gross_income,
        taxable_income=taxable_income,
        federal_income_tax=federal_income_tax,
        state_income_tax=state_income_tax,
        social_security_tax=social_security_tax,
        medicare_tax=medicare_tax,
        additional_medicare_tax=additional_medicare_tax,
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
