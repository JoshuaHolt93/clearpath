from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import re
import tempfile
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models import (
    Account,
    Category,
    CategoryRule,
    FixedExpenseItem,
    ForecastItem,
    OnboardingProfile,
    RecurringForecastTemplate,
    Transaction,
    TransactionSplit,
    User,
    VariableExpenseItem,
)


STARTER_CATEGORY_TUPLES = [
    ("Mortgage/Rent", "expense", 1800, "home_expenses"),
    ("Home/Rental Insurance", "expense", 150, "home_expenses"),
    ("Electricity", "expense", 150, "home_expenses"),
    ("Gas", "expense", 100, "home_expenses"),
    ("Water/Sewage/Trash", "expense", 100, "home_expenses"),
    ("Phone", "expense", 120, "home_expenses"),
    ("Internet", "expense", 80, "home_expenses"),
    ("Maintenance", "expense", 100, "home_expenses"),
    ("Vehicle Payments", "expense", 0, "transportation"),
    ("Auto Insurance", "expense", 150, "transportation"),
    ("Fuel/Gasoline", "expense", 220, "transportation"),
    ("Bus/Taxi", "expense", 0, "transportation"),
    ("Repairs", "expense", 75, "transportation"),
    ("Registration/License", "expense", 25, "transportation"),
    ("Tithing", "expense", 0, "charity_gifts"),
    ("Charitable Donations", "expense", 0, "charity_gifts"),
    ("Gifts Given", "expense", 0, "charity_gifts"),
    ("Health Insurance", "expense", 250, "health_wellness"),
    ("Doctor/Dentist", "expense", 100, "health_wellness"),
    ("Medicine/Prescriptions", "expense", 75, "health_wellness"),
    ("Life Insurance", "expense", 75, "health_wellness"),
    ("Gym/Fitness", "expense", 50, "health_wellness"),
    ("Health Club Dues", "expense", 0, "health_wellness"),
    ("Consumer Subscriptions", "expense", 0, "consumer_subscriptions"),
    ("Groceries", "expense", 600, "daily_living"),
    ("Personal Supplies", "expense", 75, "daily_living"),
    ("Clothing", "expense", 100, "daily_living"),
    ("Cleaning", "expense", 40, "daily_living"),
    ("Education/Lessons", "expense", 100, "daily_living"),
    ("Dining/Eating Out", "expense", 300, "daily_living"),
    ("Salon/Barber", "expense", 50, "daily_living"),
    ("Pet Food", "expense", 75, "daily_living"),
    ("Laundry", "expense", 25, "daily_living"),
    ("Rentals", "expense", 0, "entertainment"),
    ("Music", "expense", 25, "entertainment"),
    ("Books", "expense", 25, "entertainment"),
    ("Streaming Services", "expense", 50, "entertainment"),
    ("Movies/Theater/Concerts/Plays", "expense", 75, "entertainment"),
    ("Hobbies", "expense", 75, "entertainment"),
    ("Sports/Outdoor Recreation", "expense", 75, "entertainment"),
    ("Vacation/Travel", "expense", 150, "entertainment"),
    ("Emergency Fund", "expense", 0, "savings"),
    ("Transfer to Savings", "transfer", 0, "savings"),
    ("Retirement (401k, IRA)", "expense", 0, "savings"),
    ("Investments", "expense", 0, "savings"),
    ("Education Savings", "expense", 0, "savings"),
    ("Student Loans", "expense", 0, "debt_obligations"),
    ("Other Loan", "expense", 0, "debt_obligations"),
    ("Credit Cards", "expense", 0, "debt_obligations"),
    ("Credit Card Payments", "transfer", 0, "debt_obligations"),
    ("Alimony/Child Care", "expense", 0, "debt_obligations"),
    ("Federal Taxes", "expense", 0, "debt_obligations"),
    ("State/Local Taxes", "expense", 0, "debt_obligations"),
    ("Bank Fees", "expense", 0, "miscellaneous"),
    ("Other", "expense", 200, "miscellaneous"),
    ("Income", "income", 0, "miscellaneous"),
    ("Transfers", "transfer", 0, "miscellaneous"),
]

LEGACY_CATEGORY_REMAP = {
    "housing": "Mortgage/Rent",
    "utilities": "Electricity",
    "dining": "Dining/Eating Out",
    "gas": "Fuel/Gasoline",
    "shopping": "Personal Supplies",
    "entertainment": "Movies/Theater/Concerts/Plays",
    "healthcare": "Doctor/Dentist",
    "travel": "Vacation/Travel",
}

CREDIT_CARD_PAYMENT_CATEGORY_NAME = "Credit Card Payments"
ALWAYS_ENSURE_STARTER_CATEGORY_NAMES = {CREDIT_CARD_PAYMENT_CATEGORY_NAME}

DEFAULT_CATEGORY_TARGETS = {name: monthly_target for name, _kind, monthly_target, _group in STARTER_CATEGORY_TUPLES}

CREDIT_CARD_PAYMENT_TERMS = ("payment", "pymt", "autopay", "auto pay", "thank you", "epayment", "e-payment")
CREDIT_CARD_CONTEXT_TERMS = (
    "credit card",
    "creditcard",
    "citi",
    "citicard",
    "citi card",
    "capital one",
    "discover",
    "american express",
    "amex",
    "chase card",
    "barclay",
    "synchrony",
    "wells fargo card",
    "bank of america card",
)

RULE_FIELD_OPTIONS = {"description", "account", "amount", "category"}
RULE_OPERATOR_OPTIONS = {"contains", "equals", "starts_with", "ends_with", "not_contains", "gt", "gte", "lt", "lte", "between"}

TRANSACTION_DEDUP_TEXT_REPLACEMENTS = (
    (r"\bwm\s+super\s+center\b", " walmart "),
    (r"\bwm\s+supercenter\b", " walmart "),
    (r"\bwal\s+mart\b", " walmart "),
    (r"\bwalmart\s+supercenter\b", " walmart "),
    (r"\bsam'?s\s+club\b", " samsclub "),
    (r"\bmcdonald\s+s\b", " mcdonalds "),
    (r"\bchick\s+fil\s+a\b", " chickfila "),
    (r"\bwhole\s+foods\b", " wholefoods "),
    (r"\bhome\s+depot\b", " homedepot "),
    (r"\btrader\s+joe\s+s\b", " traderjoes "),
)

TRANSACTION_DEDUP_WEAK_TOKENS = {
    "center",
    "company",
    "express",
    "foods",
    "market",
    "marketplace",
    "online",
    "restaurant",
    "services",
    "store",
    "stores",
    "supercenter",
}

TRANSACTION_DEDUP_STOP_WORDS = {
    "ach",
    "auto",
    "autopay",
    "bill",
    "card",
    "checkcard",
    "co",
    "com",
    "debit",
    "fuel",
    "gas",
    "inc",
    "llc",
    "market",
    "marketplace",
    "online",
    "payment",
    "pos",
    "purchase",
    "recurring",
    "store",
    "stores",
    "supercenter",
    "sq",
    "tst",
    "the",
    "usa",
    "visa",
    "web",
    "al",
    "ak",
    "az",
    "ar",
    "ca",
    "co",
    "ct",
    "dc",
    "de",
    "fl",
    "ga",
    "hi",
    "ia",
    "id",
    "il",
    "in",
    "ks",
    "ky",
    "la",
    "ma",
    "md",
    "me",
    "mi",
    "mn",
    "mo",
    "ms",
    "mt",
    "nc",
    "nd",
    "ne",
    "nh",
    "nj",
    "nm",
    "nv",
    "ny",
    "oh",
    "ok",
    "or",
    "pa",
    "ri",
    "sc",
    "sd",
    "tn",
    "tx",
    "ut",
    "va",
    "vt",
    "wa",
    "wi",
    "wv",
    "wy",
}


def normalize_text(value: str | None) -> str:
    return " ".join((value or "").strip().lower().split())


def parse_amount(raw_value: str | int | float | None) -> float:
    if raw_value is None:
        return 0.0
    cleaned = str(raw_value).strip().replace(",", "").replace("$", "")
    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = f"-{cleaned[1:-1]}"
    return float(cleaned or 0)


def parse_flexible_date(raw_value: str) -> date:
    cleaned = (raw_value or "").strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%m-%d-%Y", "%m-%d-%y", "%Y/%m/%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Unsupported date format: {raw_value}")


def parse_date(raw_value: str) -> date:
    return parse_flexible_date(raw_value)


def infer_mapping(headers: list[str]) -> dict[str, str]:
    lowered = {header.lower(): header for header in headers}
    candidates = {
        "date": ["date", "posted date", "transaction date"],
        "description": ["description", "merchant", "details", "name"],
        "amount": ["amount", "transaction amount", "value"],
        "debit": ["debit", "withdrawal"],
        "credit": ["credit", "deposit"],
        "account": ["account", "account name", "source", "card"],
    }
    mapping = {}
    for target, options in candidates.items():
        for option in options:
            if option in lowered:
                mapping[target] = lowered[option]
                break
    return mapping


def preview_csv_content(raw_content: str) -> dict:
    content = raw_content.lstrip("\ufeff")
    if not content.strip():
        raise ValueError("The CSV file appears to be empty.")
    lines = content.splitlines()
    sample = lines[0] + "\n" + (lines[1] if len(lines) > 1 else "")
    try:
        dialect = csv.Sniffer().sniff(sample)
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(content), dialect=dialect)
    headers = reader.fieldnames or []
    if not headers:
        raise ValueError("The CSV file needs a header row.")
    rows = [row for _, row in zip(range(15), reader)]
    return {
        "headers": headers,
        "rows": rows,
        "mapping": infer_mapping(headers),
        "raw_content": content,
        "dialect": {"delimiter": dialect.delimiter, "quotechar": dialect.quotechar},
    }


def decode_csv_payload(csv_text: str | None, csv_base64: str | None) -> str:
    if csv_text is not None:
        return csv_text
    if csv_base64:
        try:
            return base64.b64decode(csv_base64).decode("utf-8-sig")
        except Exception as exc:
            raise HTTPException(status_code=422, detail="CSV payload must be valid UTF-8 text or base64-encoded UTF-8.") from exc
    raise HTTPException(status_code=422, detail="csv_text or csv_base64 is required.")


def build_import_hash(posted_date: date, description: str, amount: float, account_name: str) -> str:
    raw = f"{posted_date.isoformat()}|{normalize_text(description)}|{amount:.2f}|{normalize_text(account_name)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def is_onboarding_complete(user: User) -> bool:
    profile = user.profile
    if not profile:
        return False
    return bool((profile.income_amount or 0) > 0 or (profile.monthly_income or 0) > 0)


def require_onboarding_complete(user: User) -> None:
    if not is_onboarding_complete(user):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "onboarding_required", "message": "Complete onboarding before managing category rules."})


def used_category_ids_for_user(db: Session, user: User) -> set[int]:
    transaction_ids = {
        category_id
        for (category_id,) in db.execute(select(Transaction.category_id).where(Transaction.user_id == user.id, Transaction.category_id.is_not(None)).distinct()).all()
        if category_id
    }
    rule_ids = {
        category_id
        for (category_id,) in db.execute(select(CategoryRule.category_id).where(CategoryRule.user_id == user.id).distinct()).all()
        if category_id
    }
    split_ids = {
        category_id
        for (category_id,) in db.execute(select(TransactionSplit.category_id).where(TransactionSplit.user_id == user.id, TransactionSplit.category_id.is_not(None)).distinct()).all()
        if category_id
    }
    return transaction_ids | rule_ids | split_ids


def category_used_by_other_users(db: Session, category: Category, user: User) -> bool:
    other_transaction = db.scalar(select(Transaction.id).where(Transaction.category_id == category.id, Transaction.user_id != user.id).limit(1))
    other_rule = db.scalar(select(CategoryRule.id).where(CategoryRule.category_id == category.id, CategoryRule.user_id != user.id).limit(1))
    other_split = db.scalar(select(TransactionSplit.id).where(TransactionSplit.category_id == category.id, TransactionSplit.user_id != user.id).limit(1))
    return bool(other_transaction or other_rule or other_split)


def ensure_user_starter_categories(db: Session, user: User) -> None:
    has_default_categories = bool(db.scalar(select(Category.id).where(Category.user_id == user.id, Category.is_default.is_(True)).limit(1)))
    existing_user_categories = {
        category.name.strip().lower(): category
        for category in db.scalars(select(Category).where(Category.user_id == user.id)).all()
    }
    created = False
    for name, kind, monthly_target, group_key in STARTER_CATEGORY_TUPLES:
        if has_default_categories and name not in ALWAYS_ENSURE_STARTER_CATEGORY_NAMES:
            continue
        key = name.strip().lower()
        if key not in existing_user_categories:
            category = Category(
                user_id=user.id,
                name=name,
                kind=kind,
                monthly_target=monthly_target,
                budget_group_key=group_key,
                is_default=True,
            )
            db.add(category)
            existing_user_categories[key] = category
            created = True
    if created:
        db.commit()


def categories_for_user(db: Session, user: User) -> list[Category]:
    ensure_user_starter_categories(db, user)
    used_ids = used_category_ids_for_user(db, user)
    filters = [Category.user_id == user.id]
    if used_ids:
        filters.append(Category.id.in_(used_ids))
    categories = db.scalars(select(Category).where(or_(*filters)).order_by(Category.name.asc())).all()
    deduped: dict[str, Category] = {}
    for category in categories:
        key = category.name.strip().lower()
        existing = deduped.get(key)
        if not existing or (category.user_id == user.id and existing.user_id != user.id):
            deduped[key] = category
    return sorted(deduped.values(), key=lambda category: category.name.lower())


def category_for_user(db: Session, category_id: int | str | None, user: User) -> Category | None:
    try:
        parsed_id = int(category_id or 0)
    except (TypeError, ValueError):
        return None
    category = db.get(Category, parsed_id)
    if not category:
        return None
    if category.user_id == user.id or category.id in used_category_ids_for_user(db, user):
        return category
    if category.is_default and category.user_id is None:
        ensure_user_starter_categories(db, user)
        target_name = LEGACY_CATEGORY_REMAP.get(category.name.strip().lower(), category.name)
        target = db.scalar(select(Category).where(Category.user_id == user.id, func.lower(Category.name) == target_name.strip().lower()))
        return target or category
    return None


def category_name_available_for_user(db: Session, name: str, user: User, exclude_id: int | None = None) -> bool:
    lowered = name.strip().lower()
    for category in categories_for_user(db, user):
        if category.id != exclude_id and category.name.strip().lower() == lowered:
            return False
    return True


def category_can_manage(db: Session, category: Category, user: User) -> bool:
    if category.user_id == user.id:
        return True
    return category.user_id is None and category.id in used_category_ids_for_user(db, user) and not category_used_by_other_users(db, category, user)


def ensure_category_option(db: Session, label: str | None, user: User | None = None) -> Category | None:
    label = (label or "").strip()
    if not label:
        return None
    if user:
        ensure_user_starter_categories(db, user)
        for category in categories_for_user(db, user):
            if category.name.strip().lower() == label.lower():
                return category
    category = db.scalar(
        select(Category).where(
            func.lower(Category.name) == label.lower(),
            or_(Category.is_default.is_(True), Category.user_id.is_(None)),
        )
    )
    if category and not user:
        return category
    category = Category(user_id=user.id if user else None, name=label, kind="expense", monthly_target=0, is_default=False)
    db.add(category)
    db.flush()
    return category


def rename_planning_category_label(db: Session, old_label: str, new_label: str, user: User) -> None:
    for model in [FixedExpenseItem, VariableExpenseItem, ForecastItem, RecurringForecastTemplate]:
        for item in db.scalars(select(model).where(model.user_id == user.id, model.category_label == old_label)).all():
            item.category_label = new_label


def clear_planning_category_label(db: Session, label: str, user: User) -> None:
    for model in [FixedExpenseItem, VariableExpenseItem, ForecastItem, RecurringForecastTemplate]:
        for item in db.scalars(select(model).where(model.user_id == user.id, model.category_label == label)).all():
            item.category_label = None


def delete_category_and_reassign(db: Session, category: Category, user: User) -> Category | None:
    replacement = None
    if category.name.strip().lower() != "other":
        replacement = ensure_category_option(db, "Other", user)
        db.flush()
    for transaction in db.scalars(select(Transaction).where(Transaction.user_id == user.id, Transaction.category_id == category.id)).all():
        transaction.category_id = replacement.id if replacement else None
    if replacement:
        for split in db.scalars(select(TransactionSplit).where(TransactionSplit.user_id == user.id, TransactionSplit.category_id == category.id)).all():
            split.category_id = replacement.id
    else:
        for split in db.scalars(select(TransactionSplit).where(TransactionSplit.user_id == user.id, TransactionSplit.category_id == category.id)).all():
            db.delete(split)
    for rule in db.scalars(select(CategoryRule).where(CategoryRule.user_id == user.id, CategoryRule.category_id == category.id)).all():
        db.delete(rule)
    clear_planning_category_label(db, category.name, user)
    db.delete(category)
    return replacement


def get_or_create_account(db: Session, user: User, account_name: str | None) -> Account | None:
    if not account_name:
        return None
    normalized_name = account_name.strip()
    existing_accounts = db.scalars(select(Account).where(Account.user_id == user.id)).all()
    for account in existing_accounts:
        if (account.name or "").strip().lower() == normalized_name.lower():
            return account
    account = Account(user_id=user.id, name=normalized_name, account_type="checking")
    db.add(account)
    db.flush()
    return account


def rule_conditions(rule: CategoryRule) -> list[dict]:
    if rule.conditions_json:
        try:
            parsed = json.loads(rule.conditions_json)
            if isinstance(parsed, list):
                return [condition for condition in parsed if isinstance(condition, dict)]
        except (TypeError, ValueError):
            pass
    if rule.match_text:
        return [
            {
                "field": "description",
                "operator": rule.match_type or "contains",
                "value": rule.match_text,
                "value_secondary": "",
                "group": "primary",
            }
        ]
    return []


def normalize_rule_conditions(conditions: list[dict], legacy_match_text: str | None = None) -> tuple[str, list[dict]]:
    normalized = []
    for index, condition in enumerate(conditions):
        field = (condition.get("field") or "").strip()
        operator = (condition.get("operator") or "contains").strip()
        value = (condition.get("value") or "").strip()
        secondary_value = (condition.get("value_secondary") or "").strip()
        join = (condition.get("join") or "and").strip().lower()
        group = (condition.get("group") or "primary").strip() or "primary"
        if field not in RULE_FIELD_OPTIONS or operator not in RULE_OPERATOR_OPTIONS or not value:
            continue
        if field == "amount" and operator == "between" and not secondary_value:
            continue
        normalized.append(
            {
                "field": field,
                "operator": operator,
                "value": value,
                "value_secondary": secondary_value,
                "group": group,
                "join": "or" if join == "or" and normalized else "and",
            }
        )
    legacy_match_text = (legacy_match_text or "").strip()
    if not normalized and legacy_match_text:
        normalized.append(
            {
                "field": "description",
                "operator": "contains",
                "value": legacy_match_text,
                "value_secondary": "",
                "group": "primary",
                "join": "and",
            }
        )
    match_text = normalized[0]["value"] if normalized else legacy_match_text
    return match_text, normalized


def rule_logic_from_conditions(conditions: list[dict]) -> str:
    if len(conditions) > 1 and any((condition.get("join") or "and") == "or" for condition in conditions[1:]):
        return "custom"
    return "all"


def serialize_rule_conditions(conditions: list[dict]) -> str | None:
    return json.dumps(conditions) if conditions else None


def _text_condition_matches(actual: str, operator: str, expected: str) -> bool:
    actual_text = normalize_text(actual)
    expected_text = normalize_text(expected)
    if operator == "equals":
        return actual_text == expected_text
    if operator == "starts_with":
        return actual_text.startswith(expected_text)
    if operator == "ends_with":
        return actual_text.endswith(expected_text)
    if operator == "not_contains":
        return expected_text not in actual_text
    return expected_text in actual_text


def _amount_condition_matches(amount: float, operator: str, expected: str, secondary_expected: str = "") -> bool:
    value = abs(parse_amount(expected))
    actual = abs(amount or 0)
    if operator == "equals":
        return round(actual, 2) == round(value, 2)
    if operator == "gt":
        return actual > value
    if operator == "gte":
        return actual >= value
    if operator == "lt":
        return actual < value
    if operator == "lte":
        return actual <= value
    if operator == "between":
        upper = abs(parse_amount(secondary_expected))
        lower, upper = sorted([value, upper])
        return lower <= actual <= upper
    return round(actual, 2) == round(value, 2)


def rule_condition_matches(condition: dict, context: dict) -> bool:
    field = condition.get("field")
    operator = condition.get("operator") or "contains"
    value = condition.get("value") or ""
    if field == "amount":
        return _amount_condition_matches(context.get("amount") or 0, operator, value, condition.get("value_secondary") or "")
    if field == "account":
        return _text_condition_matches(context.get("account") or "", operator, value)
    if field == "category":
        return _text_condition_matches(context.get("category") or "", operator, value)
    return _text_condition_matches(context.get("description") or "", operator, value)


def category_rule_matches(rule: CategoryRule, context: dict) -> bool:
    conditions = rule_conditions(rule)
    if not conditions:
        return False
    logic = rule.rule_logic or "all"
    if logic == "custom" or any("join" in condition for condition in conditions[1:]):
        result = rule_condition_matches(conditions[0], context)
        for condition in conditions[1:]:
            condition_result = rule_condition_matches(condition, context)
            if (condition.get("join") or "and") == "or":
                result = result or condition_result
            else:
                result = result and condition_result
        return result
    if logic == "any":
        return any(rule_condition_matches(condition, context) for condition in conditions)
    if logic == "primary_or_category":
        primary = [condition for condition in conditions if condition.get("group") != "category_or"]
        category_or = [condition for condition in conditions if condition.get("group") == "category_or"]
        primary_match = all(rule_condition_matches(condition, context) for condition in primary) if primary else False
        category_match = any(rule_condition_matches(condition, context) for condition in category_or)
        return primary_match or category_match
    return all(rule_condition_matches(condition, context) for condition in conditions)


def rule_summary(rule: CategoryRule) -> str:
    conditions = rule_conditions(rule)
    if not conditions:
        return "No Conditions"
    if rule.rule_logic == "custom" or any("join" in condition for condition in conditions[1:]):
        summary = _condition_summary(conditions[0])
        for condition in conditions[1:]:
            joiner = " OR " if (condition.get("join") or "and") == "or" else " AND "
            summary += joiner + _condition_summary(condition)
        return summary
    joiner = " OR " if rule.rule_logic == "any" else " AND "
    return joiner.join(_condition_summary(condition) for condition in conditions)


def _condition_summary(condition: dict) -> str:
    field_labels = {"description": "Description", "account": "Account", "amount": "Amount", "category": "Current Category"}
    operator_labels = {
        "contains": "Contains",
        "equals": "Equals",
        "starts_with": "Starts With",
        "ends_with": "Ends With",
        "not_contains": "Does Not Contain",
        "gt": "Greater Than",
        "gte": "Greater Than Or Equal To",
        "lt": "Less Than",
        "lte": "Less Than Or Equal To",
        "between": "Between",
    }
    label = field_labels.get(condition.get("field"), "Description")
    operator = operator_labels.get(condition.get("operator"), "Contains")
    value = condition.get("value") or ""
    if condition.get("operator") == "between":
        return f"{label} Between {value} And {condition.get('value_secondary') or ''}"
    return f"{label} {operator} {value}"


def apply_category_rules(db: Session, user: User, description: str, account_name: str | None = None, amount: float | None = None, category_name: str | None = None) -> Category | None:
    ensure_user_starter_categories(db, user)
    context = {
        "description": description or "",
        "account": account_name or "",
        "amount": amount or 0,
        "category": category_name or "",
    }
    rules = db.scalars(
        select(CategoryRule)
        .options(joinedload(CategoryRule.category))
        .where(CategoryRule.user_id == user.id)
        .order_by(CategoryRule.created_at.desc(), CategoryRule.id.desc())
    ).all()
    for rule in rules:
        if category_rule_matches(rule, context):
            return rule.category
    return db.scalar(select(Category).where(Category.user_id == user.id, Category.name == "Other"))


def apply_rule_to_existing_transactions(db: Session, rule: CategoryRule) -> int:
    updated = 0
    transactions = db.scalars(
        select(Transaction)
        .options(joinedload(Transaction.category), joinedload(Transaction.account))
        .where(Transaction.user_id == rule.user_id)
    ).all()
    for transaction in transactions:
        context = {
            "description": transaction.description or "",
            "account": transaction.source_name or (transaction.account.name if transaction.account else ""),
            "amount": transaction.amount or 0,
            "category": transaction.category.name if transaction.category else "",
        }
        if category_rule_matches(rule, context) and transaction.category_id != rule.category_id:
            transaction.category_id = rule.category_id
            updated += 1
    return updated


def build_import_preview(db: Session, user: User, raw_content: str, mapping: dict[str, str], fallback_account: str | None = None) -> dict:
    sample = raw_content.splitlines()[0] + "\n" + (raw_content.splitlines()[1] if len(raw_content.splitlines()) > 1 else "")
    dialect = csv.Sniffer().sniff(sample)
    reader = csv.DictReader(io.StringIO(raw_content), dialect=dialect)
    parsed_rows = []
    duplicate_count = 0

    for row in reader:
        if not row.get(mapping.get("date", ""), "").strip():
            continue

        posted_date = parse_date(row[mapping["date"]])
        description = row.get(mapping.get("description", ""), "").strip() or "Imported transaction"
        account_name = (row.get(mapping.get("account", ""), "").strip() if mapping.get("account") else fallback_account) or "Imported Account"

        if mapping.get("amount"):
            amount = parse_amount(row.get(mapping["amount"]))
        else:
            debit = parse_amount(row.get(mapping.get("debit", "")))
            credit = parse_amount(row.get(mapping.get("credit", "")))
            amount = credit if credit > 0 else -abs(debit)

        import_hash = build_import_hash(posted_date, description, amount, account_name)
        if db.scalar(select(Transaction.id).where(Transaction.user_id == user.id, Transaction.import_hash == import_hash).limit(1)):
            duplicate_count += 1
            continue

        category = apply_category_rules(db, user, description, account_name=account_name, amount=amount)
        parsed_rows.append(
            {
                "posted_date": posted_date.isoformat(),
                "description": description,
                "amount": amount,
                "transaction_type": "income" if amount > 0 else "expense",
                "source_name": account_name,
                "category_id": category.id if category else None,
            }
        )

    return {
        "new_transactions": parsed_rows,
        "new_count": len(parsed_rows),
        "duplicate_count": duplicate_count,
    }


def commit_staged_transactions(db: Session, user: User, staged_transactions: list[dict]) -> list[Transaction]:
    imported: list[Transaction] = []
    for row in staged_transactions:
        posted_date = parse_date(row["posted_date"])
        description = row["description"]
        amount = float(row["amount"])
        account_name = row.get("source_name") or "Imported Account"
        import_hash = build_import_hash(posted_date, description, amount, account_name)
        if db.scalar(select(Transaction.id).where(Transaction.user_id == user.id, Transaction.import_hash == import_hash).limit(1)):
            continue
        category_id = row.get("category_id")
        category = None
        if category_id:
            category = db.scalar(
                select(Category).where(
                    Category.id == int(category_id),
                    or_(Category.user_id == user.id, Category.is_default.is_(True)),
                )
            )
        if not category:
            category = apply_category_rules(db, user, description, account_name=account_name, amount=amount)
        account = get_or_create_account(db, user, account_name)
        transaction = Transaction(
            user_id=user.id,
            account_id=account.id if account else None,
            category_id=category.id if category else None,
            posted_date=posted_date,
            description=description,
            merchant=description,
            amount=amount,
            transaction_type=row.get("transaction_type") or ("income" if amount > 0 else "expense"),
            source_name=account_name,
            import_hash=import_hash,
        )
        db.add(transaction)
        imported.append(transaction)
    db.commit()
    return imported


def staged_import_dir() -> Path:
    directory = Path(tempfile.gettempdir()) / "clearpath-api-imports"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def stage_import_rows(rows: list[dict], *, user_id: int, duplicate_count: int = 0) -> str:
    staged_id = uuid.uuid4().hex
    (staged_import_dir() / f"{staged_id}.json").write_text(
        json.dumps({"rows": rows, "duplicate_count": duplicate_count, "user_id": int(user_id)}), encoding="utf-8"
    )
    return staged_id


def load_staged_import(staged_import_id: str, *, user_id: int) -> dict | None:
    if not re.fullmatch(r"[a-f0-9]{32}", staged_import_id or ""):
        return None
    path = staged_import_dir() / f"{staged_import_id}.json"
    if not path.exists():
        return None
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict) or not isinstance(loaded.get("rows"), list):
        return None
    # Staged imports are bound to the user who created them; a payload without a
    # matching user_id is treated as not found rather than served cross-user.
    if int(loaded.get("user_id") or 0) != int(user_id):
        return None
    return {"rows": loaded["rows"], "duplicate_count": int(loaded.get("duplicate_count") or 0)}


def clear_staged_import(staged_import_id: str) -> None:
    if not re.fullmatch(r"[a-f0-9]{32}", staged_import_id or ""):
        return
    path = staged_import_dir() / f"{staged_import_id}.json"
    path.unlink(missing_ok=True)


def looks_like_credit_card_payment(
    description: str | None,
    merchant: str | None = None,
    source_name: str | None = None,
    account_name: str | None = None,
    account_type: str | None = None,
) -> bool:
    text = normalize_text(" ".join([description or "", merchant or "", source_name or "", account_name or "", account_type or ""]))
    if not text:
        return False
    has_payment_language = any(term in text for term in CREDIT_CARD_PAYMENT_TERMS)
    has_card_context = any(term in text for term in CREDIT_CARD_CONTEXT_TERMS)
    return has_payment_language and has_card_context


def transaction_amount_cents(transaction: Transaction) -> int:
    return int(round((transaction.amount or 0) * 100))


def transaction_duplicate_key(transaction: Transaction) -> tuple[date, int]:
    return transaction.posted_date, transaction_amount_cents(transaction)


def merge_duplicate_transactions_for_user(db: Session, user: User) -> int:
    duplicate_hashes = [
        import_hash
        for (import_hash,) in db.execute(
            select(Transaction.import_hash)
            .where(Transaction.user_id == user.id)
            .group_by(Transaction.import_hash)
            .having(func.count(Transaction.id) > 1)
        ).all()
    ]
    merged = 0
    other_category = db.scalar(select(Category).where(Category.user_id == user.id, Category.name == "Other"))

    for import_hash in duplicate_hashes:
        transactions = db.scalars(
            select(Transaction).where(Transaction.user_id == user.id, Transaction.import_hash == import_hash).order_by(Transaction.id.asc())
        ).all()
        plaid_transactions = [transaction for transaction in transactions if transaction.plaid_transaction_id]
        manual_transactions = [transaction for transaction in transactions if not transaction.plaid_transaction_id]
        if not manual_transactions:
            continue

        if plaid_transactions:
            canonical = sorted(
                plaid_transactions,
                key=lambda transaction: (transaction.updated_at or transaction.created_at or datetime.min, transaction.id),
                reverse=True,
            )[0]
            duplicates = manual_transactions
        else:
            canonical = manual_transactions[0]
            duplicates = manual_transactions[1:]

        for duplicate in duplicates:
            merged += _merge_transaction_duplicate(db, user, canonical, duplicate, other_category)

    merged += _merge_reconnected_plaid_duplicates(db, user, other_category)

    if merged:
        db.commit()
    return merged


def _merge_reconnected_plaid_duplicates(db: Session, user: User, other_category: Category | None) -> int:
    transactions = db.scalars(
        select(Transaction).where(Transaction.user_id == user.id).order_by(Transaction.posted_date.asc(), Transaction.id.asc())
    ).all()
    manual_by_day_amount: dict[tuple[date, int], list[Transaction]] = {}
    plaid_transactions = []
    for transaction in transactions:
        key = transaction_duplicate_key(transaction)
        if transaction.plaid_transaction_id:
            plaid_transactions.append(transaction)
        else:
            manual_by_day_amount.setdefault(key, []).append(transaction)

    merged = 0
    merged_manual_ids: set[int] = set()
    for plaid_transaction in plaid_transactions:
        key = transaction_duplicate_key(plaid_transaction)
        candidates = [
            transaction
            for transaction in manual_by_day_amount.get(key, [])
            if transaction.id not in merged_manual_ids
        ]
        scored_candidates = [
            (score, transaction)
            for transaction in candidates
            if (score := _transaction_description_match_score(plaid_transaction, transaction)) >= 0.75
        ]
        if not scored_candidates:
            continue
        scored_candidates.sort(key=lambda row: (-row[0], row[1].id))
        if len(scored_candidates) > 1 and scored_candidates[0][0] == scored_candidates[1][0] and scored_candidates[0][0] < 1:
            continue
        duplicate = scored_candidates[0][1]
        merged_manual_ids.add(duplicate.id)
        merged += _merge_transaction_duplicate(db, user, plaid_transaction, duplicate, other_category)
    return merged


def merge_transaction_pair_for_user(db: Session, user: User, first: Transaction, second: Transaction) -> Transaction:
    if first.user_id != user.id or second.user_id != user.id:
        raise ValueError("Both transactions must belong to the signed-in user.")
    if first.id == second.id:
        raise ValueError("Choose two different transactions to merge.")
    if transaction_duplicate_key(first) != transaction_duplicate_key(second):
        raise ValueError("Only transactions with the same posted date and amount can be merged.")

    canonical, duplicate = first, second
    if second.plaid_transaction_id and not first.plaid_transaction_id:
        canonical, duplicate = second, first
    other_category = db.scalar(select(Category).where(Category.user_id == user.id, Category.name == "Other"))
    _merge_transaction_duplicate(db, user, canonical, duplicate, other_category)
    db.commit()
    return canonical


def _merge_transaction_duplicate(db: Session, user: User, canonical: Transaction, duplicate: Transaction, other_category: Category | None) -> int:
    if duplicate.id == canonical.id:
        return 0
    if duplicate.category_id and (not canonical.category_id or (other_category and canonical.category_id == other_category.id)):
        canonical.category_id = duplicate.category_id
    if duplicate.notes and not canonical.notes:
        canonical.notes = duplicate.notes
    db.delete(duplicate)
    return 1


def transaction_duplicate_suggestions_for_user(db: Session, user: User, *, limit: int = 8) -> list[dict]:
    transactions = db.scalars(select(Transaction).where(Transaction.user_id == user.id).order_by(Transaction.posted_date.desc(), Transaction.id.desc())).all()
    manual_by_day_amount: dict[tuple[date, int], list[Transaction]] = {}
    plaid_transactions = []
    for transaction in transactions:
        if transaction.plaid_transaction_id:
            plaid_transactions.append(transaction)
        else:
            manual_by_day_amount.setdefault(transaction_duplicate_key(transaction), []).append(transaction)

    suggestions = []
    used_manual_ids = set()
    for plaid_transaction in plaid_transactions:
        candidates = [
            transaction
            for transaction in manual_by_day_amount.get(transaction_duplicate_key(plaid_transaction), [])
            if transaction.id not in used_manual_ids
        ]
        if not candidates:
            continue
        scored_candidates = [
            (_transaction_description_match_score(plaid_transaction, transaction), transaction)
            for transaction in candidates
        ]
        scored_candidates.sort(key=lambda row: (-row[0], row[1].id))
        best_score, best_match = scored_candidates[0]
        if len(scored_candidates) > 1 and best_score == scored_candidates[1][0] and best_score < 0.75:
            continue
        used_manual_ids.add(best_match.id)
        suggestions.append(
            {
                "plaid_transaction_id": plaid_transaction.id,
                "manual_transaction_id": best_match.id,
                "score": best_score,
                "confidence_label": "Likely Match" if best_score >= 0.75 else "Needs Review",
            }
        )
        if len(suggestions) >= limit:
            break
    return suggestions


def _transaction_description_match_score(first: Transaction, second: Transaction) -> float:
    first_text = _transaction_match_text(first)
    second_text = _transaction_match_text(second)
    if not first_text or not second_text:
        return 0
    if first_text == second_text:
        return 1
    shorter, longer = sorted([first_text, second_text], key=len)
    if len(shorter) >= 5 and shorter in longer:
        return 0.95
    first_compact = first_text.replace(" ", "")
    second_compact = second_text.replace(" ", "")
    shorter_compact, longer_compact = sorted([first_compact, second_compact], key=len)
    if len(shorter_compact) >= 5 and shorter_compact in longer_compact:
        return 0.9
    first_tokens = set(first_text.split())
    second_tokens = set(second_text.split())
    if not first_tokens or not second_tokens:
        return 0
    shared_strong_tokens = [
        token
        for token in first_tokens & second_tokens
        if _strong_transaction_match_token(token)
    ]
    if shared_strong_tokens:
        return 0.82
    overlap = len(first_tokens & second_tokens)
    return overlap / max(len(first_tokens), len(second_tokens))


def _transaction_match_text(transaction: Transaction) -> str:
    raw = transaction.merchant or transaction.description or ""
    cleaned = re.sub(r"[^a-z0-9\s]+", " ", raw.lower())
    for pattern, replacement in TRANSACTION_DEDUP_TEXT_REPLACEMENTS:
        cleaned = re.sub(pattern, replacement, cleaned)
    tokens = [
        token
        for token in cleaned.split()
        if len(token) > 1 and not token.isdigit() and token not in TRANSACTION_DEDUP_STOP_WORDS
    ]
    return " ".join(tokens)


def _strong_transaction_match_token(token: str) -> bool:
    return len(token) >= 5 and token not in TRANSACTION_DEDUP_WEAK_TOKENS


def transaction_description_match_text(transaction: Transaction) -> str:
    return (transaction.merchant or transaction.description or "").strip()


def transaction_description_match_key(transaction: Transaction) -> str:
    return normalize_text(transaction_description_match_text(transaction))


def matching_description_transactions(db: Session, user: User, transaction: Transaction) -> list[Transaction]:
    match_key = transaction_description_match_key(transaction)
    if not match_key:
        return []
    candidates = db.scalars(
        select(Transaction)
        .options(joinedload(Transaction.splits))
        .where(Transaction.user_id == user.id)
        .order_by(Transaction.posted_date.desc(), Transaction.id.desc())
    ).unique().all()
    return [
        candidate
        for candidate in candidates
        if candidate.id != transaction.id and transaction_description_match_key(candidate) == match_key
    ]


def ensure_category_rule_for_transaction_description(db: Session, user: User, transaction: Transaction, category: Category) -> bool:
    match_text = transaction_description_match_text(transaction)
    if not match_text:
        return False
    normalized_match = normalize_text(match_text)
    for rule in db.scalars(select(CategoryRule).where(CategoryRule.user_id == user.id, CategoryRule.category_id == category.id)).all():
        for condition in rule_conditions(rule):
            if (
                condition.get("field") == "description"
                and condition.get("operator") == "equals"
                and normalize_text(condition.get("value") or "") == normalized_match
            ):
                return False
    conditions = [
        {
            "field": "description",
            "operator": "equals",
            "value": match_text,
            "value_secondary": "",
            "group": "primary",
            "join": "and",
        }
    ]
    db.add(
        CategoryRule(
            user_id=user.id,
            category_id=category.id,
            match_text=match_text,
            match_type="equals",
            rule_logic="all",
            conditions_json=serialize_rule_conditions(conditions),
        )
    )
    return True


def get_owned_transaction(db: Session, user: User, transaction_id: int) -> Transaction:
    transaction = db.scalar(
        select(Transaction)
        .options(selectinload(Transaction.category), selectinload(Transaction.account), selectinload(Transaction.splits).selectinload(TransactionSplit.category))
        .where(Transaction.user_id == user.id, Transaction.id == transaction_id)
    )
    if not transaction:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found.")
    return transaction


def get_owned_rule(db: Session, user: User, rule_id: int) -> CategoryRule:
    rule = db.scalar(select(CategoryRule).options(joinedload(CategoryRule.category)).where(CategoryRule.user_id == user.id, CategoryRule.id == rule_id))
    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category rule not found.")
    return rule


def get_owned_category_for_management(db: Session, user: User, category_id: int) -> Category:
    category = category_for_user(db, category_id, user)
    if not category:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found for this account.")
    if not category_can_manage(db, category, user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="That category cannot be managed for this account.")
    return category
