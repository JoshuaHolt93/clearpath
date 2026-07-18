from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class AccountResponse(BaseModel):
    id: int
    name: str
    account_type: str
    institution: str | None = None
    current_balance: float
    cash_projection_role: str
    is_manual: bool
    plaid_account_id: str | None = None
    plaid_item_id: int | None = None
    mask: str | None = None

    model_config = ConfigDict(from_attributes=True)


class CategoryResponse(BaseModel):
    id: int
    name: str
    kind: str
    monthly_target: float
    is_default: bool
    budget_group_key: str | None = None
    budget_sort_order: int | None = None
    can_manage: bool | None = None

    model_config = ConfigDict(from_attributes=True)


class TransactionSplitResponse(BaseModel):
    id: int
    category: CategoryResponse
    amount: float
    notes: str | None = None

    model_config = ConfigDict(from_attributes=True)


class TransactionResponse(BaseModel):
    id: int
    posted_date: date
    description: str
    merchant: str | None = None
    amount: float
    transaction_type: str
    source_name: str | None = None
    import_hash: str
    notes: str | None = None
    plaid_transaction_id: str | None = None
    plaid_metadata: str | None = None
    pending: bool
    display_merchant: str
    raw_description: str | None = None
    plaid_category_label: str | None = None
    payment_channel_label: str | None = None
    location_summary: str | None = None
    category: CategoryResponse | None = None
    account: AccountResponse | None = None
    splits: list[TransactionSplitResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class TransactionBudgetActionResponse(BaseModel):
    # Flask 964c369 transaction_budget_action payload: the "make this a
    # budget" hint shown next to categorized expense transactions.
    category_name: str
    target: float
    target_label: str
    hint: str


class AmortizationActionResponse(BaseModel):
    action: str
    fixed_expense_item_id: int | None = None
    label: str
    hint: str | None = None


class DuplicateSuggestionResponse(BaseModel):
    plaid_transaction_id: int
    manual_transaction_id: int
    score: float
    confidence_label: str
    plaid_transaction: TransactionResponse
    manual_transaction: TransactionResponse


class TransactionListResponse(BaseModel):
    items: list[TransactionResponse]
    total: int
    page: int
    per_page: int
    categories: list[CategoryResponse]
    accounts: list[AccountResponse]
    duplicate_suggestions: list[DuplicateSuggestionResponse]
    budget_actions: dict[int, TransactionBudgetActionResponse] = Field(default_factory=dict)
    amortization_actions: dict[int, AmortizationActionResponse] = Field(default_factory=dict)
    # Flask 0ddefb0: page rows already linked to a recurring template.
    recurring_transaction_ids: list[int] = Field(default_factory=list)


class TransactionCreateRequest(BaseModel):
    posted_date: date
    description: str
    amount: float
    merchant: str | None = None
    account_id: int | None = None
    account_name: str | None = None
    category_id: int | None = None
    category_name: str | None = None
    notes: str | None = None


class TransactionCategoryUpdateRequest(BaseModel):
    category_id: int | None = None
    new_category_name: str | None = None
    apply_to_similar: bool = False
    # Flask 0ddefb0 mark_recurring: create/refresh a recurring expense
    # template from this transaction.
    mark_recurring: bool = False
    recurring_name: str | None = None
    recurring_start_date: str | None = None
    recurring_second_date: str | None = None
    recurring_frequency: str = "monthly"
    recurring_days_of_week: list[int | str] = Field(default_factory=list)
    recurring_monthly_week_numbers: list[int | str] = Field(default_factory=list)
    recurring_monthly_weekday: int | str | None = None


class TransactionCategoryUpdateResponse(BaseModel):
    # Mirrors the Flask update_transaction_category JSON payload (420b456
    # apply-to-similar + 964c369 budget activation).
    transaction: TransactionResponse
    updated_transaction_ids: list[int] = Field(default_factory=list)
    similar_updated_count: int = 0
    rule_created: bool = False
    created_budget_target: float | None = None
    budget_action: TransactionBudgetActionResponse | None = None
    amortization_action: AmortizationActionResponse | None = None
    recurring_message: str | None = None
    recurring_success: bool | None = None


class TransactionSplitInput(BaseModel):
    category_id: int
    amount: float
    notes: str | None = None


class TransactionSplitsUpdateRequest(BaseModel):
    clear_splits: bool = False
    splits: list[TransactionSplitInput] = Field(default_factory=list)


class DuplicateTransactionMergeRequest(BaseModel):
    first_transaction_id: int
    second_transaction_id: int


class DuplicateTransactionMergeResponse(BaseModel):
    merged: bool
    surviving_transaction: TransactionResponse
    deleted_transaction_id: int


class TransactionImportMapping(BaseModel):
    date: str
    description: str
    amount: str | None = None
    debit: str | None = None
    credit: str | None = None
    account: str | None = None


class TransactionImportPreviewRequest(BaseModel):
    csv_text: str | None = None
    csv_base64: str | None = None
    mapping: TransactionImportMapping | None = None
    fallback_account: str | None = None


class TransactionImportRow(BaseModel):
    posted_date: date
    description: str
    amount: float
    transaction_type: str
    source_name: str
    category_id: int | None = None
    category_name: str | None = None


class TransactionImportPreviewResponse(BaseModel):
    staged_import_id: str
    headers: list[str]
    sample_rows: list[dict]
    mapping: dict[str, str | None]
    new_transactions: list[TransactionImportRow]
    new_count: int
    duplicate_count: int


class TransactionImportStagedResponse(BaseModel):
    staged_import_id: str
    new_transactions: list[TransactionImportRow]
    new_count: int


class TransactionImportCommitRequest(BaseModel):
    confirm: bool = True


class TransactionImportCommitResponse(BaseModel):
    imported: int
    duplicate_count: int
    transactions: list[TransactionResponse]


class CategoryCreateRequest(BaseModel):
    name: str
    kind: str = "expense"
    # API adaptation of Flask create_category's return_to sniffing: when the
    # category is created from the transactions screen, Flask seeds an initial
    # budget target. The stateless API carries that intent explicitly.
    activate_budget: bool = False


class CategoryUpdateRequest(BaseModel):
    name: str | None = None
    kind: str | None = None


class CategoryDeleteRequest(BaseModel):
    replacement_category_id: int | None = None


class CategoryDeleteResponse(BaseModel):
    deleted_category_id: int
    replacement_category: CategoryResponse | None = None


class CategoryRuleCondition(BaseModel):
    field: str
    operator: str = "contains"
    value: str
    value_secondary: str = ""
    group: str = "primary"
    join: str = "and"


class CategoryRuleCreateRequest(BaseModel):
    category_id: int
    conditions: list[CategoryRuleCondition] = Field(default_factory=list, max_length=4)
    match_text: str | None = None


class CategoryRuleUpdateRequest(BaseModel):
    category_id: int
    conditions: list[CategoryRuleCondition] = Field(default_factory=list, max_length=4)
    match_text: str | None = None


class CategoryRuleDeleteRequest(BaseModel):
    confirm: bool = True


class CategoryRuleResponse(BaseModel):
    id: int
    category: CategoryResponse
    match_text: str
    match_type: str
    rule_logic: str
    conditions: list[dict]
    summary: str
    created_at: datetime
    updated_at: datetime
    applied_count: int | None = None


class CategoryRuleListResponse(BaseModel):
    rules: list[CategoryRuleResponse]
    categories: list[CategoryResponse]
