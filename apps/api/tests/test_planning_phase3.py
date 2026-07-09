from __future__ import annotations

from datetime import date

import pytest

from app.models import OnboardingProfile
from app.services.planning_service import (
    _monthly_weekday_occurrence,
    _occurrences_for_month,
    add_months,
    annual_salary_from_profile,
    calculate_tax_estimate,
    monthly_amount_for_frequency,
    monthly_income_from_profile,
    month_bounds,
    retirement_cash_flow_contribution,
    retirement_taxable_income_adjustment,
)


def gross_profile(**overrides) -> OnboardingProfile:
    profile = OnboardingProfile(
        income_amount=100000,
        monthly_income=0,
        income_type="salary",
        income_frequency="monthly",
        paycheck_cadence="monthly",
        income_basis="gross",
        additional_income_amount=0,
        additional_income_frequency="annual",
        tax_filing_status="single",
        include_payroll_taxes=True,
        retirement_enabled=False,
        hourly_hours_per_week=40,
    )
    for key, value in overrides.items():
        setattr(profile, key, value)
    return profile


def test_month_helpers():
    assert month_bounds(date(2026, 2, 14)) == (date(2026, 2, 1), date(2026, 2, 28))
    assert add_months(date(2026, 11, 20), 2) == date(2027, 1, 1)
    assert add_months(date(2026, 1, 31), -1) == date(2025, 12, 1)


def test_monthly_amount_for_frequency_table():
    assert monthly_amount_for_frequency(100, "weekly") == pytest.approx(100 * 52 / 12)
    assert monthly_amount_for_frequency(100, "biweekly") == pytest.approx(100 * 26 / 12)
    assert monthly_amount_for_frequency(100, "semimonthly") == pytest.approx(200)
    assert monthly_amount_for_frequency(100, "quarterly") == pytest.approx(100 * 4 / 12)
    assert monthly_amount_for_frequency(1200, "annual") == pytest.approx(100)
    assert monthly_amount_for_frequency(100, "monthly") == pytest.approx(100)
    assert monthly_amount_for_frequency(100, None) == pytest.approx(100)


def test_income_normalization_paths():
    salary = gross_profile()
    assert monthly_income_from_profile(salary) == pytest.approx(100000 / 12)

    hourly = gross_profile(income_type="hourly", income_amount=50)
    assert monthly_income_from_profile(hourly) == pytest.approx(50 * 40 * 52 / 12)

    # Legacy heuristic: a per-paycheck amount stored alongside a consistent
    # monthly figure is treated as a paycheck, not an annual salary.
    legacy = gross_profile(income_amount=2600, monthly_income=2600 * 26 / 12, paycheck_cadence="biweekly")
    assert annual_salary_from_profile(legacy) == pytest.approx(2600 * 26)
    assert monthly_income_from_profile(legacy) == pytest.approx(2600 * 26 / 12)

    with_additional = gross_profile(additional_income_amount=1200, additional_income_frequency="annual")
    assert monthly_income_from_profile(with_additional) == pytest.approx(100000 / 12 + 100)


def test_retirement_cash_flow_and_taxable_adjustment():
    profile = gross_profile(
        retirement_enabled=True,
        retirement_has_employer_plan=True,
        retirement_employer_withheld=True,
        retirement_monthly_contribution=500,
        retirement_personal_monthly_contribution=200,
    )
    # Gross basis keeps the withheld employer contribution in cash flow.
    assert retirement_cash_flow_contribution(profile) == pytest.approx(700)
    assert retirement_taxable_income_adjustment(profile) == pytest.approx(6000)

    take_home = gross_profile(
        income_basis="take_home",
        retirement_enabled=True,
        retirement_has_employer_plan=True,
        retirement_employer_withheld=True,
        retirement_monthly_contribution=500,
        retirement_personal_monthly_contribution=200,
    )
    # Take-home basis drops the already-withheld employer share.
    assert retirement_cash_flow_contribution(take_home) == pytest.approx(200)


def test_monthly_weekday_occurrence_weeks_and_last_week():
    # July 2026: the 1st is a Wednesday; Fridays fall on 3, 10, 17, 24, 31.
    july = date(2026, 7, 1)
    assert _monthly_weekday_occurrence(july, 4, 1) == date(2026, 7, 3)
    assert _monthly_weekday_occurrence(july, 4, 3) == date(2026, 7, 17)
    # Week 5 means "last occurrence of that weekday in the month".
    assert _monthly_weekday_occurrence(july, 4, 5) == date(2026, 7, 31)
    # A fifth Monday does not exist when only four fit inside the month.
    # July 2026 Mondays: 6, 13, 20, 27 -> week number 5 falls back to the last.
    assert _monthly_weekday_occurrence(july, 0, 5) == date(2026, 7, 27)
    # Week 4 Friday exists (24th); an out-of-range week returns None.
    assert _monthly_weekday_occurrence(july, 4, 4) == date(2026, 7, 24)
    assert _monthly_weekday_occurrence(july, 9, 2) is None


def test_occurrences_monthly_day_clamping_and_start_gate():
    # Day 31 clamps to the end of shorter months.
    assert _occurrences_for_month(date(2026, 1, 31), "monthly", date(2026, 2, 1)) == [date(2026, 2, 28)]
    # Months before the start date produce nothing.
    assert _occurrences_for_month(date(2026, 3, 15), "monthly", date(2026, 2, 1)) == []
    # preferred_day wins over the start date's day.
    assert _occurrences_for_month(date(2026, 1, 5), "monthly", date(2026, 4, 1), preferred_day=20) == [date(2026, 4, 20)]


def test_occurrences_biweekly_anchoring():
    # Anchored on Friday 2026-06-05, biweekly hits June 5/19 and July 3/17/31.
    assert _occurrences_for_month(date(2026, 6, 5), "biweekly", date(2026, 6, 1)) == [date(2026, 6, 5), date(2026, 6, 19)]
    assert _occurrences_for_month(date(2026, 6, 5), "biweekly", date(2026, 7, 1)) == [
        date(2026, 7, 3),
        date(2026, 7, 17),
        date(2026, 7, 31),
    ]
    # Weekday-pinned biweekly: anchor week of 2026-06-01 (Monday), Fridays of
    # even weeks since anchor -> June 5 (week 0) and June 19 (week 2).
    assert _occurrences_for_month(date(2026, 6, 1), "biweekly", date(2026, 6, 1), days_of_week="4") == [
        date(2026, 6, 5),
        date(2026, 6, 19),
    ]


def test_occurrences_semimonthly_quarterly_annual():
    # Semimonthly without an explicit second day pairs day 1 with day 15.
    assert _occurrences_for_month(date(2026, 5, 1), "semimonthly", date(2026, 5, 1)) == [date(2026, 5, 1), date(2026, 5, 15)]
    assert _occurrences_for_month(date(2026, 5, 1), "semimonthly", date(2026, 5, 1), second_day_of_month=20) == [
        date(2026, 5, 1),
        date(2026, 5, 20),
    ]
    # Quarterly fires only on 3-month offsets from the start month.
    assert _occurrences_for_month(date(2026, 1, 10), "quarterly", date(2026, 4, 1)) == [date(2026, 4, 10)]
    assert _occurrences_for_month(date(2026, 1, 10), "quarterly", date(2026, 5, 1)) == []
    # Annual fires only in the anniversary month.
    assert _occurrences_for_month(date(2025, 9, 12), "annual", date(2026, 9, 1)) == [date(2026, 9, 12)]
    assert _occurrences_for_month(date(2025, 9, 12), "annual", date(2026, 8, 1)) == []


def test_occurrences_weekly_paths():
    # Plain weekly walks in 7-day steps from the start date.
    assert _occurrences_for_month(date(2026, 6, 24), "weekly", date(2026, 7, 1)) == [
        date(2026, 7, 1),
        date(2026, 7, 8),
        date(2026, 7, 15),
        date(2026, 7, 22),
        date(2026, 7, 29),
    ]
    # Weekday-pinned weekly emits every selected weekday in the month.
    assert _occurrences_for_month(date(2026, 7, 1), "weekly", date(2026, 7, 1), days_of_week="0,4") == [
        date(2026, 7, 3),
        date(2026, 7, 6),
        date(2026, 7, 10),
        date(2026, 7, 13),
        date(2026, 7, 17),
        date(2026, 7, 20),
        date(2026, 7, 24),
        date(2026, 7, 27),
        date(2026, 7, 31),
    ]


def test_take_home_basis_produces_zero_withholding():
    estimate = calculate_tax_estimate(gross_profile(income_basis="take_home"))
    assert estimate.annual_total == 0
    assert estimate.monthly_total == 0
    assert estimate.state_method == "Take-home income entered"
    assert "Take-Home Income" in estimate.state_note


def test_tax_estimate_single_100k_no_state():
    estimate = calculate_tax_estimate(gross_profile(tax_state=None))
    # 2026 single: standard deduction 16,100 -> taxable 83,900.
    # Bracket (50,400-105,700): 5,800 base + 22% over 50,400 = 13,170.
    assert estimate.taxable_income == pytest.approx(83900)
    assert estimate.federal_income_tax == pytest.approx(13170)
    assert estimate.social_security_tax == pytest.approx(6200)
    assert estimate.medicare_tax == pytest.approx(1450)
    assert estimate.additional_medicare_tax == 0
    assert estimate.state_income_tax == 0
    assert estimate.state_method == "State not selected"
    assert estimate.annual_total == pytest.approx(13170 + 6200 + 1450)
    assert estimate.monthly_total == pytest.approx((13170 + 6200 + 1450) / 12)


def test_tax_estimate_no_income_tax_state():
    estimate = calculate_tax_estimate(gross_profile(tax_state="TX"))
    assert estimate.state_income_tax == 0
    assert estimate.state_method == "No broad wage income tax"
    assert estimate.annual_total == pytest.approx(13170 + 6200 + 1450)


def test_tax_estimate_flat_bracket_state():
    estimate = calculate_tax_estimate(gross_profile(tax_state="GA"))
    # GA 2026: single deduction 12,000, flat 5.19% -> (100,000-12,000)*0.0519.
    assert estimate.state_taxable_income == pytest.approx(88000)
    assert estimate.state_income_tax == pytest.approx(88000 * 0.0519)
    assert estimate.state_rate == pytest.approx(88000 * 0.0519 / 100000 * 100)
    assert estimate.annual_total == pytest.approx(13170 + 88000 * 0.0519 + 6200 + 1450)


def test_payroll_taxes_cap_and_thresholds():
    high_income = gross_profile(income_amount=300000)
    estimate = calculate_tax_estimate(high_income)
    # Social Security caps at the 2026 wage base; additional Medicare kicks in
    # above 200,000 for single filers.
    assert estimate.social_security_tax == pytest.approx(184500 * 0.062)
    assert estimate.medicare_tax == pytest.approx(300000 * 0.0145)
    assert estimate.additional_medicare_tax == pytest.approx(100000 * 0.009)

    no_payroll = gross_profile(include_payroll_taxes=False, tax_state="TX")
    estimate = calculate_tax_estimate(no_payroll)
    assert estimate.social_security_tax == 0
    assert estimate.medicare_tax == 0
    assert estimate.annual_total == pytest.approx(13170)
