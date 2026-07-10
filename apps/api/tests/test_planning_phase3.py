from __future__ import annotations

from datetime import date

import pytest

from app.models import FixedExpenseItem, Goal, MonthlyBudgetCategorySnapshot, OnboardingProfile, User, VariableExpenseItem
from conftest import TestingSessionLocal
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


def _register_full_user(client, email: str) -> int:
    from app.core.security import decode_token

    registered = client.post(
        "/v1/auth/register",
        json={
            "email": email,
            "password": "CorrectHorse1!",
            "display_name": "Plan User",
            "household_name": "Plan Household",
            "policy_acknowledgement": True,
        },
    )
    assert registered.status_code == 201
    completed = client.post(
        "/v1/auth/mfa/setup",
        headers={"Authorization": f"Bearer {registered.json()['access_token']}"},
        json={"action": "skip"},
    )
    assert completed.status_code == 200
    payload = decode_token(completed.json()["access_token"])
    return int(payload["user_id"]), completed.json()["access_token"]


def test_sync_monthly_plan_and_snapshot_end_to_end(client):
    from app.services.planning_service import sync_monthly_plan

    user_id, token = _register_full_user(client, "plan-sync@example.com")
    with TestingSessionLocal() as db:
        user = db.get(User, user_id)
        user.selected_plan = "basic"
        profile = user.profile
        profile.income_amount = 100000
        profile.monthly_income = 0
        profile.income_type = "salary"
        profile.income_basis = "gross"
        profile.paycheck_cadence = "monthly"
        profile.tax_filing_status = "single"
        profile.tax_state = "TX"
        profile.include_payroll_taxes = True
        profile.planned_debt_payment = 300
        profile.planned_savings_contribution = 0
        db.add(FixedExpenseItem(user_id=user_id, name="Mortgage Payment", amount=1800, start_date=date(2026, 1, 1), frequency="monthly", due_day=1, is_loan=False))
        db.add(VariableExpenseItem(user_id=user_id, name="Household Stuff", amount=200, frequency="monthly", use_specific_date=False))
        db.add(Goal(user_id=user_id, name="Emergency Fund", goal_type="savings", target_amount=10000, current_amount=0, monthly_contribution=400))
        db.commit()

    # July actuals: the mortgage cleared and one unplanned grocery run.
    for description, amount in [("Mortgage Payment", -1800.0), ("Kroger Store 214", -100.0)]:
        created = client.post(
            "/v1/transactions",
            headers={"Authorization": f"Bearer {token}"},
            json={"posted_date": "2026-07-05", "description": description, "amount": amount, "account_name": "Main Checking"},
        )
        assert created.status_code == 201

    target = date(2026, 7, 15)
    with TestingSessionLocal() as db:
        user = db.get(User, user_id)
        plan = sync_monthly_plan(db, user, target)

        # Income 100k/12; TX + single/100k taxes are 13,170 federal + 6,200 SS
        # + 1,450 Medicare = 20,820/yr -> 1,735/mo (hand-computed earlier).
        assert plan.income == pytest.approx(100000 / 12)
        assert plan.fixed_expenses == pytest.approx(1800)
        assert plan.planned_savings == pytest.approx(400)  # goal beats profile target
        assert plan.planned_debt_payment == pytest.approx(300)
        assert plan.safe_to_spend_target == pytest.approx(100000 / 12 - 1735 - 1800 - 400 - 300)

        from app.models import MonthlyBudgetSnapshot

        snapshot = db.query(MonthlyBudgetSnapshot).filter_by(user_id=user_id, month=date(2026, 7, 1)).one()
        assert snapshot.planned_taxes == pytest.approx(1735)
        assert snapshot.planned_variable_expenses == pytest.approx(200)
        assert snapshot.expected_cash_flow == pytest.approx(100000 / 12 - 1735 - 1800 - 200 - 400 - 300)
        assert snapshot.actual_fixed_expenses == pytest.approx(1800)
        # Flask commit 6371a50: transactions claimed by fixed items are
        # excluded from the variable pool, so only the grocery run remains.
        assert snapshot.actual_variable_expenses == pytest.approx(100)
        assert snapshot.actual_total_expenses == pytest.approx(1900)
        assert snapshot.budget_remaining == pytest.approx((1800 + 200 + 1735) - (1800 + 100))
        assert snapshot.net_cash_flow == pytest.approx(0 - 1900)

        category_rows = db.query(MonthlyBudgetCategorySnapshot).filter_by(user_id=user_id, month=date(2026, 7, 1)).all()
        actual_by_name = {row.category_name: row.actual for row in category_rows}
        # Both transactions defaulted to the user's Other category.
        assert actual_by_name.get("Other") == pytest.approx(1900)
        # Flask 40cf107/83ca1b6: the canonical Income category produces a
        # budget row; with no recorded income it falls back to the planned
        # profile income.
        income_rows = [row for row in category_rows if row.category_kind == "income"]
        assert [row.category_name for row in income_rows] == ["Income"]
        assert income_rows[0].planned == pytest.approx(100000 / 12)
        assert income_rows[0].actual == pytest.approx(100000 / 12)


def test_both_post_sync_hooks_registered_in_order():
    import app.services.planning_service as planning_service
    import app.services.subscription_service as subscription_service
    from app.services import plaid_service

    hooks = plaid_service.POST_SYNC_HOOKS
    assert subscription_service._plaid_post_sync_hook in hooks
    assert planning_service._plaid_post_sync_hook in hooks
    # Flask order: subscriptions rescan first, monthly plan second.
    assert hooks.index(subscription_service._plaid_post_sync_hook) < hooks.index(planning_service._plaid_post_sync_hook)


def test_additional_local_tax_joins_the_estimate():
    # Flask 40cf107: a user-labeled additional local tax adds monthly*12 to
    # the annual total on the gross basis and stays zero on take-home.
    estimate = calculate_tax_estimate(gross_profile(tax_state="TX", tax_additional_label="City Earnings Tax", tax_additional_monthly_amount=50))
    assert estimate.additional_tax_label == "City Earnings Tax"
    assert estimate.additional_tax_annual == pytest.approx(600)
    assert estimate.annual_total == pytest.approx(13170 + 6200 + 1450 + 600)
    assert estimate.monthly_total == pytest.approx((13170 + 6200 + 1450 + 600) / 12)

    take_home = calculate_tax_estimate(
        gross_profile(income_basis="take_home", tax_additional_label="City Earnings Tax", tax_additional_monthly_amount=50)
    )
    assert take_home.additional_tax_annual == 0
    assert take_home.annual_total == 0


def test_credit_card_payments_and_liability_inflows_are_not_income():
    # Flask 1a91183: credit-card payments and liability-account inflows are
    # debt paydown, not income.
    from app.models import Account, Category, Transaction
    from app.services.planning_service import account_is_liability, transaction_counts_as_income, transaction_is_credit_card_payment

    cc_category = Category(name="Credit Card Payments", kind="transfer")
    payment = Transaction(description="CITI AUTOPAY PAYMENT", amount=250, category=cc_category, splits=[])
    assert transaction_is_credit_card_payment(payment)
    assert transaction_counts_as_income(payment) is False

    heuristic_payment = Transaction(description="AMEX EPAYMENT THANK YOU", amount=125, category=None, splits=[])
    assert transaction_is_credit_card_payment(heuristic_payment)
    assert transaction_counts_as_income(heuristic_payment) is False

    liability_account = Account(name="Citi Double Cash", account_type="credit card", is_manual=True)
    assert account_is_liability(liability_account)
    refund = Transaction(description="Statement credit", amount=25, category=None, account=liability_account, splits=[])
    assert transaction_counts_as_income(refund) is False

    checking = Account(name="Main Checking", account_type="checking", is_manual=True)
    income_category = Category(name="Income", kind="income")
    paycheck = Transaction(description="Payroll Deposit", amount=3100, category=income_category, account=checking, splits=[])
    assert transaction_counts_as_income(paycheck) is True
