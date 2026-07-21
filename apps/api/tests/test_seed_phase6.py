from __future__ import annotations

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
)
from app.services.auth_service import ETHICS_POLICY_VERSION
from app.services.seed_service import DEMO_EMAIL, DEMO_PASSWORD, ensure_defaults, seed_demo_user


def test_ensure_defaults_creates_default_categories_idempotently(db):
    ensure_defaults(db)
    defaults = db.query(Category).filter(Category.user_id.is_(None)).all()
    assert defaults, "expected default categories to be seeded"
    assert all(category.is_default for category in defaults)
    # Legacy names the demo data relies on are present as user_id=None defaults.
    names = {category.name for category in defaults}
    assert {"Income", "Groceries", "Housing", "Gas", "Dining", "Utilities", "Shopping", "Entertainment"}.issubset(names)
    # "Gas" exists in both the starter set and the legacy set; the dedup keeps one.
    assert len([category for category in defaults if category.name == "Gas"]) == 1

    count_before = len(defaults)
    ensure_defaults(db)
    assert db.query(Category).filter(Category.user_id.is_(None)).count() == count_before


def test_seed_demo_user_creates_full_household_and_is_idempotent(db):
    user = seed_demo_user(db)
    assert user is not None
    assert user.email == DEMO_EMAIL
    assert user.check_password(DEMO_PASSWORD)
    assert user.ethics_policy_version == ETHICS_POLICY_VERSION
    assert user.ethics_acknowledged_at is not None

    assert db.query(OnboardingProfile).filter_by(user_id=user.id).count() == 1
    assert db.query(Account).filter_by(user_id=user.id).count() == 2
    assert db.query(Transaction).filter_by(user_id=user.id).count() == 10
    assert db.query(CategoryRule).filter_by(user_id=user.id).count() == 3
    assert db.query(Goal).filter_by(user_id=user.id).count() == 2
    assert db.query(FixedExpenseItem).filter_by(user_id=user.id).count() == 3
    assert db.query(VariableExpenseItem).filter_by(user_id=user.id).count() == 3
    assert db.query(RecurringForecastTemplate).filter_by(user_id=user.id).count() == 2

    # Hand-checked demo figures.
    profile = db.query(OnboardingProfile).filter_by(user_id=user.id).one()
    assert profile.income_amount == 74400
    assert profile.paycheck_cadence == "semimonthly"
    transactions = db.query(Transaction).filter_by(user_id=user.id).all()
    assert sum(t.amount for t in transactions if t.amount > 0) == 3100
    assert any(t.description == "Kroger Store 214" and round(t.amount, 2) == -142.16 for t in transactions)

    # Idempotent: a second run seeds nothing new.
    assert seed_demo_user(db) is None
    assert db.query(User).filter_by(email=DEMO_EMAIL).count() == 1
    assert db.query(Transaction).filter_by(user_id=user.id).count() == 10
