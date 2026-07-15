from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.feature_access import user_has_feature
from app.core.planning_constants import REVOLVING_DEBT_ACCOUNT_TYPES
from app.models import (
    Account,
    Category,
    FixedExpenseItem,
    ForecastItem,
    LoanPlan,
    RecurringForecastTemplate,
    Transaction,
    User,
    VariableExpenseItem,
)
from app.services.planning_service import (
    app_today,
    initial_budget_target_for_transaction_category,
    loan_category_for_item,
    monthly_amount_for_fixed_item,
    monthly_income_from_profile,
    selected_loan_extra_payment_total,
    sync_loan_fixed_expense_budget,
)
from app.services.transaction_service import categories_for_user, normalize_text

MORTGAGE_RENT_CATEGORY_LABEL = "Mortgage/Rent"


def category_is_mortgage_rent(category: Category | None) -> bool:
    return bool(category and normalize_text(category.name or "") == normalize_text(MORTGAGE_RENT_CATEGORY_LABEL))


def mortgage_loan_items_for_category(
    db: Session,
    user: User,
    category_label: str | None,
) -> list[FixedExpenseItem]:
    category_key = normalize_text(category_label or "")
    if not category_key:
        return []
    items = db.scalars(
        select(FixedExpenseItem)
        .where(FixedExpenseItem.user_id == user.id)
        .order_by(FixedExpenseItem.created_at.asc(), FixedExpenseItem.id.asc())
    ).all()
    return [
        item
        for item in items
        if normalize_text(item.category_label or item.name or "") == category_key
        and loan_category_for_item(item)
    ]


def matching_mortgage_loan_item(
    db: Session,
    user: User,
    category_label: str | None,
    *,
    name: str | None = None,
    amount: float | None = None,
) -> FixedExpenseItem | None:
    candidates = mortgage_loan_items_for_category(db, user, category_label)
    name_key = normalize_text(name or "")
    if name_key:
        for item in candidates:
            if normalize_text(item.name or "") == name_key:
                return item
    if amount and amount > 0:
        for item in candidates:
            if abs(monthly_amount_for_fixed_item(item) - amount) < 0.01:
                return item
    return candidates[0] if len(candidates) == 1 else None


def mortgage_payment_name_from_transaction(transaction: Transaction) -> str:
    name = (transaction.display_merchant or transaction.description or "").strip()
    return name[:120] if name else "Mortgage Payment"


def mortgage_payment_name_from_category(category: Category) -> str:
    return "Mortgage Payment" if category_is_mortgage_rent(category) else f"{category.name} Payment"


def ensure_mortgage_loan_item_from_transaction(
    db: Session,
    transaction: Transaction,
    user: User,
) -> tuple[FixedExpenseItem, bool]:
    amount = abs(transaction.amount or 0)
    item_name = mortgage_payment_name_from_transaction(transaction)
    item = matching_mortgage_loan_item(
        db,
        user,
        MORTGAGE_RENT_CATEGORY_LABEL,
        name=item_name,
        amount=amount,
    )
    if item:
        item.is_loan = True
        sync_loan_fixed_expense_budget(db, item, user, force=True)
        return item, False

    start_date = transaction.posted_date or app_today()
    item = FixedExpenseItem(
        user_id=user.id,
        name=item_name,
        amount=amount,
        due_day=start_date.day,
        start_date=start_date,
        frequency="monthly",
        category_label=MORTGAGE_RENT_CATEGORY_LABEL,
        is_loan=True,
        notes="Created from a Mortgage/Rent transaction.",
    )
    db.add(item)
    sync_loan_fixed_expense_budget(db, item, user, force=True)
    return item, True


def ensure_mortgage_loan_item_from_category(
    db: Session,
    category: Category,
    user: User,
) -> tuple[FixedExpenseItem, bool]:
    item_name = mortgage_payment_name_from_category(category)
    amount = max(category.monthly_target or 0, 0)
    item = matching_mortgage_loan_item(db, user, category.name, name=item_name, amount=amount)
    if item:
        item.is_loan = True
        sync_loan_fixed_expense_budget(db, item, user, force=True)
        return item, False

    if amount <= 0:
        amount = initial_budget_target_for_transaction_category(db, category, user)
    start_date = app_today()
    item = FixedExpenseItem(
        user_id=user.id,
        name=item_name,
        amount=amount,
        due_day=start_date.day,
        start_date=start_date,
        frequency="monthly",
        category_label=category.name,
        is_loan=True,
        notes="Created from the Mortgage/Rent budget.",
    )
    db.add(item)
    sync_loan_fixed_expense_budget(db, item, user, force=True)
    return item, True


def transaction_amortization_action(
    db: Session,
    transaction: Transaction,
    user: User,
) -> dict | None:
    if not user_has_feature(user, "mortgage_loan_planning"):
        return None
    if (transaction.amount or 0) >= 0 or not category_is_mortgage_rent(transaction.category):
        return None
    item = matching_mortgage_loan_item(
        db,
        user,
        MORTGAGE_RENT_CATEGORY_LABEL,
        name=mortgage_payment_name_from_transaction(transaction),
        amount=abs(transaction.amount or 0),
    )
    return {
        "action": "open" if item else "create",
        "fixed_expense_item_id": item.id if item else None,
        "label": "Open Amortization Schedule" if item else "Create Amortization Schedule",
        "hint": (
            "Open mortgage payoff scenarios for this Mortgage/Rent transaction."
            if item
            else "Start a mortgage payoff schedule from this Mortgage/Rent transaction."
        ),
    }


def budget_amortization_action(db: Session, category: Category | None, user: User) -> dict | None:
    if not category_is_mortgage_rent(category) or not user_has_feature(user, "mortgage_loan_planning"):
        return None
    item = matching_mortgage_loan_item(db, user, category.name)
    return {
        "action": "open" if item else "create",
        "fixed_expense_item_id": item.id if item else None,
        "label": "Open Amortization Schedule" if item else "Create Amortization Schedule",
    }


def account_is_revolving_debt(account: Account) -> bool:
    account_type = normalize_text(account.account_type or "")
    normalized_type = account_type.replace("_", " ")
    if account_type in REVOLVING_DEBT_ACCOUNT_TYPES or normalized_type in REVOLVING_DEBT_ACCOUNT_TYPES:
        return True
    account_label = normalize_text(f"{account.name or ''} {account.institution or ''}")
    return any(keyword in account_label for keyword in ["credit card", "card account", "line of credit", "heloc"])


def account_has_planned_debt_payment(account: Account, planned_debt_items: list[FixedExpenseItem]) -> bool:
    account_text = normalize_text(" ".join([account.name or "", account.institution or "", account.mask or ""]))
    account_tokens = {token for token in re.split(r"[^a-z0-9]+", account_text) if len(token) >= 4}
    is_credit_card_account = account_is_revolving_debt(account)
    for item in planned_debt_items:
        item_text = normalize_text(" ".join([item.name or "", item.category_label or ""]))
        if not item_text:
            continue
        if is_credit_card_account and any(token in item_text for token in ["credit card", "card payment", "debt payment"]):
            return True
        if account_text and (account_text in item_text or item_text in account_text):
            return True
        if account_tokens and any(token in item_text for token in account_tokens):
            return True
    return False


def estimated_revolving_account_debt_payments(
    db: Session,
    user: User,
    planned_debt_items: list[FixedExpenseItem] | None = None,
) -> float:
    planned_debt_items = planned_debt_items if planned_debt_items is not None else [
        item
        for item in db.scalars(select(FixedExpenseItem).where(FixedExpenseItem.user_id == user.id)).all()
        if loan_category_for_item(item)
    ]
    total = 0.0
    for account in db.scalars(select(Account).where(Account.user_id == user.id)).all():
        if not account_is_revolving_debt(account):
            continue
        balance = abs(account.current_balance or 0)
        if balance <= 0 or account_has_planned_debt_payment(account, planned_debt_items):
            continue
        total += min(balance, max(balance * 0.02, 25.0))
    return total


def debt_to_income_ratio(db: Session, user: User) -> float:
    income = monthly_income_from_profile(user.profile)
    if income <= 0:
        return 0.0
    loan_payment_total = 0.0
    planned_debt_items = []
    for item in db.scalars(select(FixedExpenseItem).where(FixedExpenseItem.user_id == user.id)).all():
        if loan_category_for_item(item):
            planned_debt_items.append(item)
            loan_payment_total += monthly_amount_for_fixed_item(item)
    loan_payment_total += selected_loan_extra_payment_total(db, user)
    loan_payment_total += estimated_revolving_account_debt_payments(db, user, planned_debt_items)
    return loan_payment_total / income


def loan_category_label_options_for_user(db: Session, user: User) -> list[str]:
    preferred_labels = ["Mortgage/Rent", "Vehicle Payments", "Student Loans", "Other Loan", "Credit Cards"]
    labels = preferred_labels + [category.name for category in categories_for_user(db, user)]
    labels.extend(
        item.category_label
        for model in (FixedExpenseItem, VariableExpenseItem, ForecastItem, RecurringForecastTemplate)
        for item in db.scalars(select(model).where(model.user_id == user.id)).all()
        if item.category_label
    )
    deduped = {}
    for label in labels:
        normalized = normalize_text(label)
        if not normalized:
            continue
        is_loan_label = any(
            token in normalized
            for token in ["mortgage", "loan", "vehicle payment", "auto payment", "car payment", "credit card", "debt"]
        )
        if is_loan_label and normalized not in deduped:
            deduped[normalized] = label
    return list(deduped.values())
