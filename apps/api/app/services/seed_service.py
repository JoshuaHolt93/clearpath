from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.planning_constants import LEGACY_DEFAULT_CATEGORIES, STARTER_CATEGORIES
from app.models import (
    Account,
    Category,
    CategoryRule,
    FixedExpenseItem,
    Goal,
    OnboardingProfile,
    RecurringForecastTemplate,
    Transaction,
    User,
    VariableExpenseItem,
    utc_now,
)
from app.services.auth_service import ETHICS_POLICY_VERSION
from app.services.planning_service import app_today
from app.services.transaction_service import build_import_hash

# Faithful port of Flask app/seed.py at 92ccdbc. The demo user uses the port's
# canonical ETHICS_POLICY_VERSION (auth_service) so it matches every other
# port-created account, and password hashing goes through User.set_password
# (app/core/passwords.py) per the migration's hard constraint.

DEMO_EMAIL = "demo@clearpath.local"
DEMO_PASSWORD = "SampleVault123!"


def ensure_defaults(db: Session) -> None:
    starter_categories = [(category["name"], category["kind"], category["monthly_target"]) for category in STARTER_CATEGORIES]
    starter_names = {category[0] for category in starter_categories}
    default_categories = starter_categories + [legacy for legacy in LEGACY_DEFAULT_CATEGORIES if legacy[0] not in starter_names]
    for name, kind, monthly_target in default_categories:
        category = db.scalar(select(Category).where(Category.name == name, Category.user_id.is_(None)))
        if not category:
            db.add(Category(user_id=None, name=name, kind=kind, monthly_target=monthly_target, is_default=True))
        elif not category.is_default:
            category.is_default = True
    db.commit()


def seed_demo_user(db: Session) -> User | None:
    ensure_defaults(db)
    if db.scalar(select(User).where(User.email == DEMO_EMAIL)):
        return None

    user = User(
        email=DEMO_EMAIL,
        household_name="Demo Household",
        ethics_acknowledged_at=utc_now(),
        ethics_policy_version=ETHICS_POLICY_VERSION,
    )
    user.set_password(DEMO_PASSWORD)
    db.add(user)
    db.flush()

    today = app_today()
    next_demo_pay_date = today.replace(day=15) if today.day < 15 else (today.replace(day=28) if today.day < 28 else today + timedelta(days=14))

    db.add(
        OnboardingProfile(
            user_id=user.id,
            income_amount=74400,
            income_type="salary",
            income_frequency="semimonthly",
            paycheck_cadence="semimonthly",
            next_pay_date=next_demo_pay_date,
            hourly_hours_per_week=40,
            monthly_income=6200,
            fixed_expenses=2800,
            planned_savings_contribution=500,
            planned_debt_payment=300,
            target_investment_contribution=250,
        )
    )

    checking = Account(user_id=user.id, name="Main Checking", current_balance=4800, account_type="checking")
    savings = Account(user_id=user.id, name="Emergency Savings", current_balance=12500, account_type="savings")
    db.add_all([checking, savings])
    db.flush()

    categories = {category.name: category for category in db.scalars(select(Category).where(Category.user_id.is_(None))).all()}
    sample_transactions = [
        (today - timedelta(days=20), "Payroll Deposit", 3100, "Income", checking.id),
        (today - timedelta(days=19), "Rent Payment", -1800, "Housing", checking.id),
        (today - timedelta(days=16), "Kroger Store 214", -142.16, "Groceries", checking.id),
        (today - timedelta(days=14), "Shell Oil 0442", -58.02, "Gas", checking.id),
        (today - timedelta(days=12), "Netflix", -18.99, "Entertainment", checking.id),
        (today - timedelta(days=10), "Spotify", -11.99, "Entertainment", checking.id),
        (today - timedelta(days=8), "Local Bistro", -76.40, "Dining", checking.id),
        (today - timedelta(days=6), "City Electric", -92.00, "Utilities", checking.id),
        (today - timedelta(days=4), "Target", -64.29, "Shopping", checking.id),
        (today - timedelta(days=2), "Family Diner", -82.30, "Dining", checking.id),
    ]
    for posted_date, description, amount, category_name, account_id in sample_transactions:
        account = checking if account_id == checking.id else savings
        db.add(
            Transaction(
                user_id=user.id,
                account_id=account.id,
                category_id=categories[category_name].id,
                posted_date=posted_date,
                description=description,
                merchant=description,
                amount=amount,
                transaction_type="income" if amount > 0 else "expense",
                source_name=account.name,
                import_hash=build_import_hash(posted_date, description, amount, account.name),
            )
        )

    db.add_all(
        [
            CategoryRule(user_id=user.id, category_id=categories["Groceries"].id, match_text="kroger"),
            CategoryRule(user_id=user.id, category_id=categories["Gas"].id, match_text="shell"),
            CategoryRule(user_id=user.id, category_id=categories["Dining"].id, match_text="diner"),
        ]
    )

    db.add_all(
        [
            Goal(user_id=user.id, name="Emergency Fund", goal_type="savings", target_amount=15000, current_amount=12500, monthly_contribution=400),
            Goal(user_id=user.id, name="Credit Card Payoff", goal_type="debt", target_amount=4200, current_amount=1600, monthly_contribution=300),
        ]
    )

    db.add_all(
        [
            FixedExpenseItem(user_id=user.id, name="Rent", amount=1800, due_day=1),
            FixedExpenseItem(user_id=user.id, name="Utilities", amount=220, due_day=12),
            FixedExpenseItem(user_id=user.id, name="Insurance", amount=180, due_day=18),
            VariableExpenseItem(user_id=user.id, name="Groceries", amount=600),
            VariableExpenseItem(user_id=user.id, name="Gas", amount=220),
            VariableExpenseItem(user_id=user.id, name="Kids and school extras", amount=180),
            RecurringForecastTemplate(user_id=user.id, name="Paycheck", amount=1550, item_type="income", frequency="semimonthly", start_date=today.replace(day=1), second_day_of_month=15, category_label="Income"),
            RecurringForecastTemplate(user_id=user.id, name="Quarterly insurance", amount=360, item_type="expense", frequency="quarterly", start_date=today.replace(day=10), category_label="Insurance"),
        ]
    )

    db.commit()
    return user
