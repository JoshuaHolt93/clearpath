from __future__ import annotations

from datetime import date

import pytest

from app.models import OnboardingProfile
from app.services.planning_service import (
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
