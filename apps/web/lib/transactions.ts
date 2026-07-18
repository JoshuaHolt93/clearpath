import type { components } from "@clearpath/api-client";
import { transactionImportPreviewViewSchema, transactionReviewViewSchema } from "@clearpath/validation";

type ApiMe = components["schemas"]["MeResponse"];
type ApiList = components["schemas"]["TransactionListResponse"];
type ApiTransaction = components["schemas"]["TransactionResponse"];
type ApiCategory = components["schemas"]["CategoryResponse"];
type ApiAccount = components["schemas"]["AccountResponse"];
type ApiPlaid = components["schemas"]["PlaidItemListResponse"];
type ApiPreview = components["schemas"]["TransactionImportPreviewResponse"];

function mapSession(data: ApiMe) {
  return {
    ownerUserId: data.id,
    householdName: data.household_name ?? null,
    selectedPlan: data.selected_plan,
    billingStatus: data.billing_status,
    planDisplayName: data.plan_display_name,
    primaryAccountHolder: data.primary_account_holder,
    subject: {
      id: data.session_subject.id,
      subjectType: data.session_subject.subject_type,
      email: data.session_subject.email,
      displayName: data.session_subject.display_name,
      firstName: data.session_subject.first_name,
      avatarInitial: data.session_subject.avatar_initial,
      householdRole: data.session_subject.household_role ?? null,
    },
    featureAccess: (data.feature_access ?? []).map((row) => ({
      feature: row.feature,
      enabled: row.enabled,
      hidden: row.hidden,
      requiredPlan: row.required_plan,
    })),
  };
}

function mapCategory(row: ApiCategory) {
  return {
    id: row.id,
    name: row.name,
    kind: row.kind,
    monthlyTarget: row.monthly_target,
    isDefault: row.is_default,
    budgetGroupKey: row.budget_group_key ?? null,
    budgetSortOrder: row.budget_sort_order ?? null,
    canManage: row.can_manage ?? false,
  };
}

function mapAccount(row: ApiAccount) {
  return {
    id: row.id,
    name: row.name,
    accountType: row.account_type,
    institution: row.institution ?? null,
    currentBalance: row.current_balance,
    isManual: row.is_manual,
    mask: row.mask ?? null,
  };
}

export function mapTransaction(row: ApiTransaction) {
  return {
    id: row.id,
    postedDate: row.posted_date,
    description: row.description,
    displayMerchant: row.display_merchant,
    rawDescription: row.raw_description ?? null,
    amount: row.amount,
    transactionType: row.transaction_type,
    sourceName: row.source_name ?? null,
    notes: row.notes ?? null,
    plaidTransactionId: row.plaid_transaction_id ?? null,
    plaidCategoryLabel: row.plaid_category_label ?? null,
    paymentChannelLabel: row.payment_channel_label ?? null,
    locationSummary: row.location_summary ?? null,
    pending: row.pending,
    category: row.category ? mapCategory(row.category) : null,
    account: row.account ? mapAccount(row.account) : null,
    splits: (row.splits ?? []).map((split) => ({
      id: split.id,
      category: mapCategory(split.category),
      amount: split.amount,
      notes: split.notes ?? null,
    })),
  };
}

export function mapTransactionReview(data: ApiList, me: ApiMe, plaid: ApiPlaid) {
  return transactionReviewViewSchema.safeParse({
    session: mapSession(me),
    items: data.items.map(mapTransaction),
    total: data.total,
    page: data.page,
    perPage: data.per_page,
    categories: data.categories.map(mapCategory),
    accounts: data.accounts.map(mapAccount),
    duplicateSuggestions: data.duplicate_suggestions.map((row) => ({
      plaidTransactionId: row.plaid_transaction_id,
      manualTransactionId: row.manual_transaction_id,
      score: row.score,
      confidenceLabel: row.confidence_label,
      plaidTransaction: mapTransaction(row.plaid_transaction),
      manualTransaction: mapTransaction(row.manual_transaction),
    })),
    budgetActions: Object.fromEntries(Object.entries(data.budget_actions ?? {}).map(([id, row]) => [id, {
      categoryName: row.category_name,
      target: row.target,
      targetLabel: row.target_label,
      hint: row.hint,
    }])),
    amortizationActions: Object.fromEntries(Object.entries(data.amortization_actions ?? {}).map(([id, row]) => [id, {
      action: row.action,
      fixedExpenseItemId: row.fixed_expense_item_id ?? null,
      label: row.label,
      hint: row.hint ?? null,
    }])),
    recurringTransactionIds: data.recurring_transaction_ids ?? [],
    plaidItems: plaid.items.map((item) => ({
      id: item.id,
      institutionName: item.institution_name ?? null,
      status: item.status,
      lastSyncedAt: item.last_synced_at ?? null,
      errorMessage: item.error_message ?? null,
      reconnectRequiredAt: item.reconnect_required_at ?? null,
      accounts: (item.accounts ?? []).map(mapAccount),
    })),
  });
}

export function mapTransactionImportPreview(data: ApiPreview) {
  return transactionImportPreviewViewSchema.safeParse({
    stagedImportId: data.staged_import_id,
    headers: data.headers,
    sampleRows: data.sample_rows,
    mapping: {
      date: data.mapping.date ?? "",
      description: data.mapping.description ?? "",
      amount: data.mapping.amount ?? null,
      debit: data.mapping.debit ?? null,
      credit: data.mapping.credit ?? null,
      account: data.mapping.account ?? null,
    },
    newTransactions: data.new_transactions.map((row) => ({
      postedDate: row.posted_date,
      description: row.description,
      amount: row.amount,
      transactionType: row.transaction_type,
      sourceName: row.source_name,
      categoryId: row.category_id ?? null,
      categoryName: row.category_name ?? null,
    })),
    newCount: data.new_count,
    duplicateCount: data.duplicate_count,
  });
}
