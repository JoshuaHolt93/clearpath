from __future__ import annotations

import calendar
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.planning_constants import DEFAULT_CATEGORY_TARGETS
from app.models import Category, PlaidItem, Transaction, User
from app.services.planning_service import (
    app_today,
    budget_category_match_terms,
    editable_budget_category_for_user,
    monthly_income_from_profile,
    sync_monthly_plan,
)
from app.services.transaction_service import (
    CREDIT_CARD_PAYMENT_CATEGORY_NAME,
    categories_for_user,
    looks_like_credit_card_payment,
    normalize_text,
)


def visible_plaid_items_for_user(db: Session, user: User) -> list[PlaidItem]:
    return list(
        db.scalars(
            select(PlaidItem)
            .where(
                PlaidItem.user_id == user.id,
                PlaidItem.status != "disconnected",
                PlaidItem.disconnected_at.is_(None),
            )
            .order_by(PlaidItem.created_at.desc())
        ).all()
    )


def transaction_looks_like_credit_card_payment(transaction: Transaction) -> bool:
    account = transaction.account
    return looks_like_credit_card_payment(
        transaction.description,
        transaction.merchant,
        transaction.source_name,
        account.name if account else None,
        account.account_type if account else None,
    )


def suggested_category_for_transaction(transaction: Transaction, categories: list[Category]) -> Category | None:
    if (transaction.amount or 0) >= 0:
        if transaction_looks_like_credit_card_payment(transaction):
            return next(
                (
                    category
                    for category in categories
                    if category.kind == "transfer"
                    and category.name.strip().lower() == CREDIT_CARD_PAYMENT_CATEGORY_NAME.lower()
                ),
                None,
            )
        return next(
            (
                category
                for category in categories
                if category.kind == "income" and category.name.strip().lower() == "income"
            ),
            None,
        )

    if transaction_looks_like_credit_card_payment(transaction):
        return next(
            (
                category
                for category in categories
                if category.kind == "transfer"
                and category.name.strip().lower() == CREDIT_CARD_PAYMENT_CATEGORY_NAME.lower()
            ),
            None,
        )

    haystack = normalize_text(
        " ".join([transaction.description or "", transaction.merchant or "", transaction.source_name or ""])
    )
    if not haystack:
        return None

    best_category = None
    best_score = 0
    for category in categories:
        if category.kind != "expense" or category.name.strip().lower() == "other":
            continue
        score = sum(1 for term in budget_category_match_terms(category.name) if term and term in haystack)
        if score > best_score:
            best_category = category
            best_score = score
    return best_category if best_score > 0 else None


def auto_categorize_onboarding_transactions(db: Session, user: User, categories: list[Category]) -> int:
    transactions = list(
        db.scalars(
            select(Transaction)
            .options(joinedload(Transaction.category), joinedload(Transaction.account))
            .where(Transaction.user_id == user.id, Transaction.amount < 0)
            .order_by(Transaction.posted_date.desc(), Transaction.id.desc())
            .limit(150)
        ).unique().all()
    )
    updated = 0
    for transaction in transactions:
        current_name = (transaction.category.name if transaction.category else "").strip().lower()
        if current_name not in {"", "other"}:
            continue
        suggested = suggested_category_for_transaction(transaction, categories)
        if suggested and transaction.category_id != suggested.id:
            transaction.category_id = suggested.id
            updated += 1
    if updated:
        db.commit()
        sync_monthly_plan(db, user, purpose="monthly_plan")
        db.expire_all()
    return updated


def onboarding_training_transactions_for_user(
    db: Session,
    user: User,
    categories: list[Category],
    *,
    limit: int = 10,
) -> list[Transaction]:
    other_ids = {category.id for category in categories if category.name.strip().lower() == "other"}
    recent = list(
        db.scalars(
            select(Transaction)
            .options(joinedload(Transaction.category), joinedload(Transaction.account))
            .where(Transaction.user_id == user.id, Transaction.amount < 0)
            .order_by(Transaction.posted_date.desc(), Transaction.id.desc())
            .limit(80)
        ).unique().all()
    )
    selected: list[Transaction] = []
    selected_ids: set[int] = set()

    def append(transaction: Transaction) -> None:
        if len(selected) >= limit or transaction.id in selected_ids:
            return
        selected.append(transaction)
        selected_ids.add(transaction.id)

    for transaction in recent:
        if not transaction.category_id or transaction.category_id in other_ids:
            append(transaction)
    seen_category_ids: set[int] = set()
    for transaction in recent:
        if transaction.category_id and transaction.category_id not in seen_category_ids:
            append(transaction)
            seen_category_ids.add(transaction.category_id)
    for transaction in recent:
        append(transaction)
    return selected


def seed_initial_budgets_from_onboarding(db: Session, user: User) -> int:
    today = app_today()
    month_start = today.replace(day=1)
    month_end = month_start.replace(day=calendar.monthrange(month_start.year, month_start.month)[1])
    categorized_expenses = list(
        db.scalars(
            select(Transaction)
            .options(joinedload(Transaction.category))
            .where(
                Transaction.user_id == user.id,
                Transaction.posted_date >= month_start,
                Transaction.posted_date <= month_end,
                Transaction.amount < 0,
                Transaction.category_id.is_not(None),
            )
        ).unique().all()
    )
    totals_by_category: dict[int, float] = defaultdict(float)
    categories_by_id: dict[int, Category] = {}
    for transaction in categorized_expenses:
        category = transaction.category
        if not category or category.kind != "expense" or category.name.strip().lower() == "other":
            continue
        totals_by_category[category.id] += abs(transaction.amount or 0)
        categories_by_id[category.id] = category

    updated = 0
    profile = user.profile
    income_source = (profile.monthly_income if profile else 0) or monthly_income_from_profile(profile)
    income_target = round(max(income_source, 0), 2)
    if income_target > 0:
        income_category = next(
            (
                category
                for category in categories_for_user(db, user)
                if category.kind == "income" and category.name.strip().lower() == "income"
            ),
            None,
        )
        if income_category:
            editable_income = editable_budget_category_for_user(db, income_category, user)
            if round(editable_income.monthly_target or 0, 2) != income_target or editable_income.is_default:
                editable_income.monthly_target = income_target
                editable_income.is_default = False
                updated += 1

    for category_id, actual in totals_by_category.items():
        category = categories_by_id[category_id]
        editable_category = editable_budget_category_for_user(db, category, user)
        rounded_actual = ((int(actual) + 24) // 25) * 25
        target = max(DEFAULT_CATEGORY_TARGETS.get(category.name, 0), rounded_actual, 25)
        if editable_category.monthly_target != target or editable_category.is_default:
            editable_category.monthly_target = target
            editable_category.is_default = False
            updated += 1
    if updated:
        db.commit()
        sync_monthly_plan(db, user, purpose="monthly_plan")
        db.expire_all()
    return updated
