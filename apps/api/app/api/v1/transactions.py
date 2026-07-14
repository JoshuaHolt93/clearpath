from __future__ import annotations

import calendar
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.database import get_db
from app.dependencies import Principal, require_household_access
from app.models import Account, Category, CategoryRule, Transaction, TransactionSplit
from app.schemas.planning import TransactionBudgetActivateResponse
from app.schemas.transactions import (
    AccountResponse,
    CategoryCreateRequest,
    CategoryDeleteRequest,
    CategoryDeleteResponse,
    CategoryResponse,
    CategoryUpdateRequest,
    CategoryRuleCreateRequest,
    CategoryRuleDeleteRequest,
    CategoryRuleListResponse,
    CategoryRuleResponse,
    CategoryRuleUpdateRequest,
    DuplicateTransactionMergeRequest,
    DuplicateTransactionMergeResponse,
    TransactionBudgetActionResponse,
    TransactionCategoryUpdateRequest,
    TransactionCategoryUpdateResponse,
    TransactionCreateRequest,
    TransactionImportCommitRequest,
    TransactionImportCommitResponse,
    TransactionImportPreviewRequest,
    TransactionImportPreviewResponse,
    TransactionImportStagedResponse,
    TransactionListResponse,
    TransactionResponse,
    TransactionSplitsUpdateRequest,
)
from app.services.planning_service import (
    activate_transaction_budget_category,
    active_budget_categories_by_key,
    category_can_be_transaction_budget,
    create_recurring_template_from_transaction,
    initial_budget_target_for_transaction_category,
    recurring_transaction_ids_for_page,
    sync_monthly_plan,
    transaction_budget_action,
)
from app.services.transaction_service import (
    apply_category_rules,
    apply_rule_to_existing_transactions,
    build_import_hash,
    build_import_preview,
    category_can_manage,
    category_for_user,
    category_name_available_for_user,
    categories_for_user,
    clear_staged_import,
    commit_staged_transactions,
    decode_csv_payload,
    delete_category_and_reassign,
    ensure_category_option,
    ensure_category_rule_for_transaction_description,
    get_or_create_account,
    get_owned_category_for_management,
    get_owned_rule,
    get_owned_transaction,
    load_staged_import,
    matching_description_transactions,
    merge_transaction_pair_for_user,
    rename_planning_category_label,
    normalize_rule_conditions,
    normalize_text,
    parse_amount,
    preview_csv_content,
    require_onboarding_complete,
    rule_conditions,
    rule_logic_from_conditions,
    rule_summary,
    serialize_rule_conditions,
    stage_import_rows,
    transaction_duplicate_suggestions_for_user,
)

router = APIRouter(tags=["transactions"])


def category_response(db: Session, user, category: Category) -> CategoryResponse:
    response = CategoryResponse.model_validate(category)
    response.can_manage = category_can_manage(db, category, user)
    return response


def account_response(account: Account) -> AccountResponse:
    return AccountResponse.model_validate(account)


def transaction_response(transaction: Transaction) -> TransactionResponse:
    return TransactionResponse.model_validate(transaction)


def rule_response(rule: CategoryRule, *, applied_count: int | None = None) -> CategoryRuleResponse:
    return CategoryRuleResponse(
        id=rule.id,
        category=CategoryResponse.model_validate(rule.category),
        match_text=rule.match_text,
        match_type=rule.match_type,
        rule_logic=rule.rule_logic,
        conditions=rule_conditions(rule),
        summary=rule_summary(rule),
        created_at=rule.created_at,
        updated_at=rule.updated_at,
        applied_count=applied_count,
    )


@router.get("/transactions", response_model=TransactionListResponse)
def list_transactions(
    principal: Annotated[Principal, Depends(require_household_access("viewer"))],
    db: Annotated[Session, Depends(get_db)],
    q: str = "",
    category_id: int | None = None,
    category_ids: list[int] = Query(default_factory=list),
    category_names: str = "",
    account_ids: list[int] = Query(default_factory=list),
    min_amount: str = "",
    max_amount: str = "",
    month: str = "",
    ids: str = "",
    page: int = 1,
    per_page: int = 20,
) -> TransactionListResponse:
    user = principal.user
    categories = categories_for_user(db, user)
    allowed_category_ids = {category.id for category in categories}
    selected_category_ids: list[int] = []
    if category_id:
        category_ids.append(category_id)
    for raw_category_id in category_ids:
        category = category_for_user(db, raw_category_id, user)
        if category and category.id in allowed_category_ids and category.id not in selected_category_ids:
            selected_category_ids.append(category.id)
    category_name_list = [value.strip() for value in category_names.split(",") if value.strip()]
    if category_name_list:
        named_category_ids = [category.id for category in categories if category.name in category_name_list]
        selected_category_ids.extend(category_id for category_id in named_category_ids if category_id not in selected_category_ids)
        if not named_category_ids:
            selected_category_ids = [-1]

    query = (
        select(Transaction)
        .options(selectinload(Transaction.category), selectinload(Transaction.account), selectinload(Transaction.splits).selectinload(TransactionSplit.category))
        .where(Transaction.user_id == user.id)
    )
    transaction_ids = [int(value) for value in ids.split(",") if value.strip().isdigit()]
    if transaction_ids:
        query = query.where(Transaction.id.in_(transaction_ids))
    if selected_category_ids:
        query = query.where(
            or_(
                Transaction.category_id.in_(selected_category_ids),
                Transaction.splits.any(TransactionSplit.category_id.in_(selected_category_ids)),
            )
        )
    if account_ids:
        query = query.where(Transaction.account_id.in_(account_ids))
    try:
        if min_amount:
            query = query.where(func.abs(Transaction.amount) >= parse_amount(min_amount))
        if max_amount:
            query = query.where(func.abs(Transaction.amount) <= parse_amount(max_amount))
    except ValueError:
        pass
    if month:
        try:
            start = datetime.strptime(month + "-01", "%Y-%m-%d").date()
            end = start.replace(day=calendar.monthrange(start.year, start.month)[1])
            query = query.where(Transaction.posted_date >= start, Transaction.posted_date <= end)
        except ValueError:
            pass

    rows = db.scalars(query.order_by(Transaction.posted_date.desc(), Transaction.id.desc())).all()
    if q:
        normalized_search = q.lower().strip()
        rows = [
            transaction
            for transaction in rows
            if normalized_search
            in " ".join(
                [
                    transaction.description or "",
                    transaction.merchant or "",
                    transaction.source_name or "",
                ]
            ).lower()
        ]
    total = len(rows)
    page = max(page, 1)
    per_page = min(max(per_page, 1), 100)
    start_index = (page - 1) * per_page
    items = rows[start_index : start_index + per_page]
    accounts = db.scalars(select(Account).where(Account.user_id == user.id)).all()
    accounts = sorted(accounts, key=lambda account: ((account.institution or "").lower(), (account.name or "").lower()))
    # Flask 964c369: budget-activation hints for the visible page rows.
    active_budget_keys = set(active_budget_categories_by_key(db, user))
    budget_actions = {
        transaction.id: TransactionBudgetActionResponse(**action)
        for transaction in items
        if transaction.id
        for action in [transaction_budget_action(db, transaction, user, active_budget_keys=active_budget_keys)]
        if action
    }
    return TransactionListResponse(
        items=[transaction_response(transaction) for transaction in items],
        total=total,
        page=page,
        per_page=per_page,
        categories=[category_response(db, user, category) for category in categories],
        accounts=[account_response(account) for account in accounts],
        duplicate_suggestions=transaction_duplicate_suggestions_for_user(db, user),
        budget_actions=budget_actions,
        recurring_transaction_ids=sorted(recurring_transaction_ids_for_page(db, user, items)),
    )


@router.post("/transactions", response_model=TransactionResponse, status_code=status.HTTP_201_CREATED)
def create_transaction(
    payload: TransactionCreateRequest,
    principal: Annotated[Principal, Depends(require_household_access("editor"))],
    db: Annotated[Session, Depends(get_db)],
) -> TransactionResponse:
    user = principal.user
    account = db.get(Account, payload.account_id) if payload.account_id else None
    if account and account.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found.")
    account = account or get_or_create_account(db, user, payload.account_name)
    category = category_for_user(db, payload.category_id, user) if payload.category_id else None
    if not category and payload.category_name:
        category = ensure_category_option(db, payload.category_name, user)
    if not category:
        category = apply_category_rules(db, user, payload.description, account_name=account.name if account else payload.account_name, amount=payload.amount)
    account_name = account.name if account else (payload.account_name or "Manual")
    transaction = Transaction(
        user_id=user.id,
        account_id=account.id if account else None,
        category_id=category.id if category else None,
        posted_date=payload.posted_date,
        description=payload.description.strip() or "Imported transaction",
        merchant=(payload.merchant or payload.description).strip(),
        amount=payload.amount,
        transaction_type="income" if payload.amount > 0 else "expense",
        source_name=account_name,
        import_hash=build_import_hash(payload.posted_date, payload.description, payload.amount, account_name),
        notes=payload.notes,
    )
    db.add(transaction)
    db.commit()
    db.refresh(transaction)
    return transaction_response(get_owned_transaction(db, user, transaction.id))


@router.post("/transaction-imports/preview", response_model=TransactionImportPreviewResponse)
def preview_transaction_import(
    payload: TransactionImportPreviewRequest,
    principal: Annotated[Principal, Depends(require_household_access("editor"))],
    db: Annotated[Session, Depends(get_db)],
) -> TransactionImportPreviewResponse:
    raw_content = decode_csv_payload(payload.csv_text, payload.csv_base64)
    try:
        preview = preview_csv_content(raw_content)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    mapping = payload.mapping.model_dump(exclude_none=True) if payload.mapping else preview["mapping"]
    if not mapping.get("date") or not mapping.get("description") or (not mapping.get("amount") and not mapping.get("debit")):
        raise HTTPException(status_code=422, detail="Map at least date, description, and either amount or debit/credit columns.")
    result = build_import_preview(db, principal.user, raw_content, mapping, fallback_account=(payload.fallback_account or "").strip() or "Imported Account")
    staged_id = stage_import_rows(result["new_transactions"], user_id=principal.user.id, duplicate_count=result["duplicate_count"])
    rows = [
        {**row, "category_name": db.get(Category, row["category_id"]).name if row.get("category_id") else None}
        for row in result["new_transactions"]
    ]
    return TransactionImportPreviewResponse(
        staged_import_id=staged_id,
        headers=preview["headers"],
        sample_rows=preview["rows"],
        mapping={key: mapping.get(key) for key in ["date", "description", "amount", "debit", "credit", "account"]},
        new_transactions=rows,
        new_count=result["new_count"],
        duplicate_count=result["duplicate_count"],
    )


@router.get("/transaction-imports/{staged_import_id}", response_model=TransactionImportStagedResponse)
def get_staged_transaction_import(
    staged_import_id: str,
    principal: Annotated[Principal, Depends(require_household_access("editor"))],
    db: Annotated[Session, Depends(get_db)],
) -> TransactionImportStagedResponse:
    staged = load_staged_import(staged_import_id, user_id=principal.user.id)
    if staged is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Staged import not found.")
    rows = [
        {**row, "category_name": db.get(Category, row["category_id"]).name if row.get("category_id") else None}
        for row in staged["rows"]
    ]
    return TransactionImportStagedResponse(staged_import_id=staged_import_id, new_transactions=rows, new_count=len(rows))


@router.post("/transaction-imports/{staged_import_id}/commit", response_model=TransactionImportCommitResponse)
def commit_transaction_import(
    staged_import_id: str,
    payload: TransactionImportCommitRequest,
    principal: Annotated[Principal, Depends(require_household_access("editor"))],
    db: Annotated[Session, Depends(get_db)],
) -> TransactionImportCommitResponse:
    if not payload.confirm:
        raise HTTPException(status_code=422, detail="Import confirmation is required.")
    staged = load_staged_import(staged_import_id, user_id=principal.user.id)
    if staged is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Staged import not found.")
    imported = commit_staged_transactions(db, principal.user, staged["rows"])
    clear_staged_import(staged_import_id)
    return TransactionImportCommitResponse(imported=len(imported), duplicate_count=staged["duplicate_count"] + (len(staged["rows"]) - len(imported)), transactions=[transaction_response(transaction) for transaction in imported])


@router.post("/transactions/duplicates/merge", response_model=DuplicateTransactionMergeResponse)
def merge_duplicate_transactions(
    payload: DuplicateTransactionMergeRequest,
    principal: Annotated[Principal, Depends(require_household_access("editor"))],
    db: Annotated[Session, Depends(get_db)],
) -> DuplicateTransactionMergeResponse:
    first = get_owned_transaction(db, principal.user, payload.first_transaction_id)
    second = get_owned_transaction(db, principal.user, payload.second_transaction_id)
    try:
        surviving = merge_transaction_pair_for_user(db, principal.user, first, second)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    deleted_id = second.id if surviving.id == first.id else first.id
    return DuplicateTransactionMergeResponse(merged=True, surviving_transaction=transaction_response(get_owned_transaction(db, principal.user, surviving.id)), deleted_transaction_id=deleted_id)


@router.patch("/transactions/{transaction_id}/category", response_model=TransactionCategoryUpdateResponse)
def update_transaction_category(
    transaction_id: int,
    payload: TransactionCategoryUpdateRequest,
    principal: Annotated[Principal, Depends(require_household_access("editor"))],
    db: Annotated[Session, Depends(get_db)],
) -> TransactionCategoryUpdateResponse:
    transaction = get_owned_transaction(db, principal.user, transaction_id)
    category = None
    created_new_category = False
    created_budget_target: float | None = None
    updated_transaction_ids: list[int] = []
    similar_updated_count = 0
    rule_created = False
    if payload.new_category_name:
        name = payload.new_category_name.strip()
        if not name:
            raise HTTPException(status_code=422, detail="Enter a category name.")
        if len(name) > 80:
            raise HTTPException(status_code=422, detail="Category names must be 80 characters or fewer.")
        if not category_name_available_for_user(db, name, principal.user):
            raise HTTPException(status_code=422, detail="That category already exists.")
        category = Category(user_id=principal.user.id, name=name, kind="income" if transaction.amount > 0 else "expense", monthly_target=0, is_default=False)
        db.add(category)
        db.flush()
        created_new_category = True
    elif payload.category_id:
        category = category_for_user(db, payload.category_id, principal.user)
    if not category:
        raise HTTPException(status_code=422, detail="Choose a category available to this account.")
    if transaction.category_id != category.id and transaction.splits:
        transaction.splits.clear()
    transaction.category_id = category.id
    updated_transaction_ids.append(transaction.id)
    # Flask 964c369: a brand-new expense category starts as a budget row.
    if created_new_category and category_can_be_transaction_budget(category):
        _, created_budget_target = activate_transaction_budget_category(db, category, principal.user, transaction)
    # Flask 420b456: optionally recategorize matching descriptions and learn a rule.
    if payload.apply_to_similar:
        for matching_transaction in matching_description_transactions(db, principal.user, transaction):
            if matching_transaction.splits:
                continue
            if matching_transaction.category_id != category.id:
                matching_transaction.category_id = category.id
                similar_updated_count += 1
            updated_transaction_ids.append(matching_transaction.id)
        rule_created = ensure_category_rule_for_transaction_description(db, principal.user, transaction, category)
    recurring_message: str | None = None
    recurring_success: bool | None = None
    if payload.mark_recurring:
        recurring_message, recurring_success = create_recurring_template_from_transaction(
            db,
            principal.user,
            transaction,
            category,
            recurring_name=payload.recurring_name,
            recurring_start_date=payload.recurring_start_date,
            recurring_second_date=payload.recurring_second_date,
            recurring_frequency=payload.recurring_frequency,
            recurring_days_of_week=payload.recurring_days_of_week,
            recurring_monthly_week_numbers=payload.recurring_monthly_week_numbers,
            recurring_monthly_weekday=payload.recurring_monthly_weekday,
        )
    db.commit()
    sync_monthly_plan(db, principal.user)
    db.expire_all()
    transaction = get_owned_transaction(db, principal.user, transaction.id)
    budget_action = transaction_budget_action(db, transaction, principal.user)
    # PHASE 3 (loans): Flask HEAD also returns amortization_action (fc97040);
    # it ports with the loan-plan endpoints.
    return TransactionCategoryUpdateResponse(
        transaction=transaction_response(transaction),
        updated_transaction_ids=updated_transaction_ids,
        similar_updated_count=similar_updated_count,
        rule_created=rule_created,
        created_budget_target=created_budget_target,
        budget_action=TransactionBudgetActionResponse(**budget_action) if budget_action else None,
        recurring_message=recurring_message,
        recurring_success=recurring_success,
    )


@router.post("/transactions/{transaction_id}/budget-category", response_model=TransactionBudgetActivateResponse)
def activate_transaction_budget(
    transaction_id: int,
    principal: Annotated[Principal, Depends(require_household_access("editor"))],
    db: Annotated[Session, Depends(get_db)],
) -> TransactionBudgetActivateResponse:
    require_onboarding_complete(principal.user)
    transaction = get_owned_transaction(db, principal.user, transaction_id)
    category = transaction.category
    if not category_can_be_transaction_budget(category):
        raise HTTPException(status_code=422, detail="Choose an expense category before making a budget.")
    if normalize_text(category.name or "") in active_budget_categories_by_key(db, principal.user):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"{category.name} is already on Budgets.")

    editable_category, target = activate_transaction_budget_category(db, category, principal.user, transaction)
    db.commit()
    sync_monthly_plan(db, principal.user, purpose="monthly_plan")
    return TransactionBudgetActivateResponse(category=CategoryResponse.model_validate(editable_category), target=target)


@router.patch("/transactions/{transaction_id}/splits", response_model=TransactionResponse)
def update_transaction_splits(
    transaction_id: int,
    payload: TransactionSplitsUpdateRequest,
    principal: Annotated[Principal, Depends(require_household_access("editor"))],
    db: Annotated[Session, Depends(get_db)],
) -> TransactionResponse:
    transaction = get_owned_transaction(db, principal.user, transaction_id)
    if payload.clear_splits:
        transaction.splits.clear()
        db.commit()
        db.expire_all()
        return transaction_response(get_owned_transaction(db, principal.user, transaction.id))
    splits = []
    for split in payload.splits:
        category = category_for_user(db, split.category_id, principal.user)
        if not category:
            raise HTTPException(status_code=422, detail="Choose a category for each split line.")
        if split.amount <= 0:
            raise HTTPException(status_code=422, detail="Split amounts must be greater than zero.")
        splits.append((category, round(split.amount, 2), split.notes))
    if len(splits) < 2:
        raise HTTPException(status_code=422, detail="Add at least two split lines, or use the category selector for a single category.")
    transaction_total = round(abs(transaction.amount or 0), 2)
    split_total = round(sum(amount for _category, amount, _notes in splits), 2)
    if abs(split_total - transaction_total) > 0.01:
        raise HTTPException(status_code=422, detail=f"Split amounts must total ${transaction_total:,.2f}.")
    transaction.splits.clear()
    for category, amount, notes in splits:
        db.add(TransactionSplit(user_id=principal.user.id, transaction_id=transaction.id, category_id=category.id, amount=amount, notes=notes))
    transaction.category_id = splits[0][0].id
    db.commit()
    db.expire_all()
    return transaction_response(get_owned_transaction(db, principal.user, transaction.id))


@router.post("/categories", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
def create_category(
    payload: CategoryCreateRequest,
    principal: Annotated[Principal, Depends(require_household_access("editor"))],
    db: Annotated[Session, Depends(get_db)],
) -> CategoryResponse:
    require_onboarding_complete(principal.user)
    name = payload.name.strip()
    kind = (payload.kind or "expense").strip().lower()
    if kind not in {"expense", "income"}:
        kind = "expense"
    if not name:
        raise HTTPException(status_code=422, detail="Enter a category name.")
    if not category_name_available_for_user(db, name, principal.user):
        raise HTTPException(status_code=422, detail="That category already exists.")
    category = Category(user_id=principal.user.id, name=name, kind=kind, monthly_target=0, is_default=False)
    # Flask 964c369: creating an expense category from the transactions screen
    # seeds an initial budget target (activate_budget replaces return_to sniffing).
    if kind == "expense" and payload.activate_budget:
        category.monthly_target = initial_budget_target_for_transaction_category(db, category, principal.user)
    db.add(category)
    db.commit()
    if category.monthly_target > 0:
        sync_monthly_plan(db, principal.user, purpose="monthly_plan")
    db.refresh(category)
    return category_response(db, principal.user, category)


@router.patch("/categories/{category_id}", response_model=CategoryResponse)
def update_category(
    category_id: int,
    payload: CategoryUpdateRequest,
    principal: Annotated[Principal, Depends(require_household_access("editor"))],
    db: Annotated[Session, Depends(get_db)],
) -> CategoryResponse:
    category = get_owned_category_for_management(db, principal.user, category_id)
    old_name = category.name
    new_name = (payload.name or "").strip()
    if not new_name:
        raise HTTPException(status_code=422, detail="Category name is required.")
    if not category_name_available_for_user(db, new_name, principal.user, exclude_id=category.id):
        raise HTTPException(status_code=422, detail="A category with that name already exists. Rename or delete the duplicate first.")
    category.name = new_name
    category.kind = payload.kind or category.kind
    if category.user_id is None:
        category.user_id = principal.user.id
    # Flask rename_category: planning worksheets follow the rename.
    rename_planning_category_label(db, old_name, new_name, principal.user)
    db.commit()
    sync_monthly_plan(db, principal.user)
    return category_response(db, principal.user, category)


@router.delete("/categories/{category_id}", response_model=CategoryDeleteResponse)
def delete_category(
    category_id: int,
    payload: CategoryDeleteRequest,
    principal: Annotated[Principal, Depends(require_household_access("editor"))],
    db: Annotated[Session, Depends(get_db)],
) -> CategoryDeleteResponse:
    category = get_owned_category_for_management(db, principal.user, category_id)
    replacement = delete_category_and_reassign(db, category, principal.user)
    db.commit()
    sync_monthly_plan(db, principal.user)
    return CategoryDeleteResponse(deleted_category_id=category_id, replacement_category=category_response(db, principal.user, replacement) if replacement else None)


@router.get("/category-rules", response_model=CategoryRuleListResponse)
def list_category_rules(
    principal: Annotated[Principal, Depends(require_household_access("viewer"))],
    db: Annotated[Session, Depends(get_db)],
) -> CategoryRuleListResponse:
    categories = categories_for_user(db, principal.user)
    rules = db.scalars(select(CategoryRule).options(selectinload(CategoryRule.category)).where(CategoryRule.user_id == principal.user.id).order_by(CategoryRule.created_at.desc(), CategoryRule.id.desc())).all()
    return CategoryRuleListResponse(rules=[rule_response(rule) for rule in rules], categories=[category_response(db, principal.user, category) for category in categories])


@router.post("/category-rules", response_model=CategoryRuleResponse, status_code=status.HTTP_201_CREATED)
def create_category_rule(
    payload: CategoryRuleCreateRequest,
    principal: Annotated[Principal, Depends(require_household_access("editor"))],
    db: Annotated[Session, Depends(get_db)],
) -> CategoryRuleResponse:
    require_onboarding_complete(principal.user)
    category = category_for_user(db, payload.category_id, principal.user)
    if not category:
        raise HTTPException(status_code=422, detail="At least one rule condition and a category are required.")
    match_text, conditions = normalize_rule_conditions([condition.model_dump() for condition in payload.conditions], payload.match_text)
    if not conditions:
        raise HTTPException(status_code=422, detail="At least one rule condition and a category are required.")
    rule = CategoryRule(
        user_id=principal.user.id,
        category_id=category.id,
        match_text=match_text,
        match_type=conditions[0].get("operator", "contains"),
        rule_logic=rule_logic_from_conditions(conditions),
        conditions_json=serialize_rule_conditions(conditions),
    )
    db.add(rule)
    db.flush()
    applied_count = apply_rule_to_existing_transactions(db, rule)
    db.commit()
    db.refresh(rule)
    # Flask add_rule/auto_rules refresh the monthly plan after applying.
    sync_monthly_plan(db, principal.user, purpose="monthly_plan")
    return rule_response(get_owned_rule(db, principal.user, rule.id), applied_count=applied_count)


@router.patch("/category-rules/{rule_id}", response_model=CategoryRuleResponse)
def update_category_rule(
    rule_id: int,
    payload: CategoryRuleUpdateRequest,
    principal: Annotated[Principal, Depends(require_household_access("editor"))],
    db: Annotated[Session, Depends(get_db)],
) -> CategoryRuleResponse:
    rule = get_owned_rule(db, principal.user, rule_id)
    category = category_for_user(db, payload.category_id, principal.user)
    match_text, conditions = normalize_rule_conditions([condition.model_dump() for condition in payload.conditions], payload.match_text)
    if not conditions or not category:
        raise HTTPException(status_code=422, detail="At least one rule condition and a category are required.")
    rule.match_text = match_text
    rule.match_type = conditions[0].get("operator", "contains")
    rule.rule_logic = rule_logic_from_conditions(conditions)
    rule.conditions_json = serialize_rule_conditions(conditions)
    rule.category_id = category.id
    applied_count = apply_rule_to_existing_transactions(db, rule)
    db.commit()
    return rule_response(get_owned_rule(db, principal.user, rule.id), applied_count=applied_count)


@router.delete("/category-rules/{rule_id}", response_model=CategoryRuleResponse)
def delete_category_rule(
    rule_id: int,
    payload: CategoryRuleDeleteRequest,
    principal: Annotated[Principal, Depends(require_household_access("editor"))],
    db: Annotated[Session, Depends(get_db)],
) -> CategoryRuleResponse:
    rule = get_owned_rule(db, principal.user, rule_id)
    response = rule_response(rule)
    db.delete(rule)
    db.commit()
    return response
