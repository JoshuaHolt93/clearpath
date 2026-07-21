import { beforeEach, describe, expect, it, vi } from "vitest";

import { PATCH as updateCategory } from "./[transactionId]/category/route";
import { PATCH as updateSplits } from "./[transactionId]/splits/route";
import { POST as mergeDuplicates } from "./duplicates/merge/route";
import { GET } from "./route";
import { POST as previewImport } from "../transaction-imports/preview/route";

const apiGet = vi.hoisted(() => vi.fn());
const apiPost = vi.hoisted(() => vi.fn());
const apiPatch = vi.hoisted(() => vi.fn());
const apiDelete = vi.hoisted(() => vi.fn());

vi.mock("@clearpath/api-client", () => ({ createClearPathClient: () => ({ GET: apiGet, POST: apiPost, PATCH: apiPatch, DELETE: apiDelete }) }));

function ok(data: unknown, status = 200) { return { data, error: undefined, response: new Response(null, { status }) }; }

function category() { return { id: 4, name: "Groceries", kind: "expense", monthly_target: 500, is_default: false, budget_group_key: "daily", budget_sort_order: 2, can_manage: true }; }
function account() { return { id: 8, name: "Main Checking", account_type: "checking", institution: "Primary Bank", current_balance: 1800, cash_projection_role: "auto", is_manual: false, plaid_account_id: "acct-8", plaid_item_id: 3, mask: "1234" }; }
function transaction(id = 21) { return { id, posted_date: "2026-07-18", description: "MARKET 104", merchant: "Local Market", amount: -63.45, transaction_type: "expense", source_name: "Main Checking", import_hash: `hash-${id}`, notes: null, plaid_transaction_id: `plaid-${id}`, plaid_metadata: "{}", pending: false, display_merchant: "Local Market", raw_description: "MARKET 104", plaid_category_label: "Food And Drink Groceries", payment_channel_label: "In Store", location_summary: "Raleigh, NC - Store 104", category: category(), account: account(), splits: [] }; }
function meResponse() { return { id: 1, email: "owner@example.com", display_name: "Owner User", household_name: "Owner Home", selected_plan: "premium", billing_status: "active", is_admin: false, session_subject: { id: 1, subject_type: "user", email: "owner@example.com", display_name: "Owner User", first_name: "Owner", avatar_initial: "O", household_role: null }, primary_account_holder: true, plan_display_name: "Premier", feature_access: [] }; }

function listResponse() {
  return { items: [transaction()], total: 1, page: 1, per_page: 20, categories: [category()], accounts: [account()], duplicate_suggestions: [{ plaid_transaction_id: 21, manual_transaction_id: 22, score: .95, confidence_label: "High confidence", plaid_transaction: transaction(21), manual_transaction: { ...transaction(22), plaid_transaction_id: null } }], budget_actions: { 21: { category_name: "Groceries", target: 75, target_label: "$75", hint: "Start this monthly budget." } }, amortization_actions: {}, recurring_transaction_ids: [21] };
}

describe("Transaction Review BFF", () => {
  beforeEach(() => { apiGet.mockReset(); apiPost.mockReset(); apiPatch.mockReset(); apiDelete.mockReset(); });

  it("combines transactions, session, and Plaid resources without syncing on GET", async () => {
    apiGet.mockImplementation((path: string) => {
      if (path === "/v1/transactions") return Promise.resolve(ok(listResponse()));
      if (path === "/v1/me") return Promise.resolve(ok(meResponse()));
      return Promise.resolve(ok({ items: [{ id: 3, institution_name: "Primary Bank", institution_id: "ins_3", status: "connected", last_synced_at: "2026-07-18T14:00:00Z", error_code: null, error_message: null, reconnect_required_at: null, disconnected_at: null, consent_acknowledged_at: null, accounts: [account()] }], ignored_accounts: [] }));
    });
    const response = await GET(new Request("http://localhost/api/transactions?q=market&category_id=4&sort=amount_desc", { headers: { cookie: "clearpath_session=full" } }));
    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({ items: [{ displayMerchant: "Local Market", rawDescription: "MARKET 104", locationSummary: "Raleigh, NC - Store 104" }], duplicateSuggestions: [{ plaidTransaction: { id: 21 }, manualTransaction: { id: 22 } }], budgetActions: { 21: { target: 75 } }, plaidItems: [{ institutionName: "Primary Bank" }] });
    expect(apiGet).toHaveBeenCalledWith("/v1/transactions", expect.objectContaining({ params: { query: expect.objectContaining({ q: "market", category_ids: [4], sort: "amount_desc" }) } }));
    expect(apiPost).not.toHaveBeenCalled();
  });

  it("forwards category learning and recurring cadence fields", async () => {
    apiPatch.mockResolvedValue(ok({ transaction: transaction(), updated_transaction_ids: [21, 22], similar_updated_count: 1, rule_created: true, created_budget_target: null, budget_action: null, amortization_action: null, recurring_message: "Recurring expense saved.", recurring_success: true }));
    const response = await updateCategory(new Request("http://localhost/api/transactions/21/category", { method: "PATCH", headers: { "content-type": "application/json" }, body: JSON.stringify({ categoryId: 4, newCategoryName: null, applyToSimilar: true, markRecurring: true, recurringName: "Local Market", recurringStartDate: "2026-08-01", recurringSecondDate: null, recurringFrequency: "biweekly", recurringDaysOfWeek: [4], recurringMonthlyWeekNumbers: [], recurringMonthlyWeekday: null }) }), { params: Promise.resolve({ transactionId: "21" }) });
    expect(response.status).toBe(200);
    expect(apiPatch).toHaveBeenCalledWith("/v1/transactions/{transaction_id}/category", expect.objectContaining({ body: expect.objectContaining({ apply_to_similar: true, mark_recurring: true, recurring_frequency: "biweekly", recurring_days_of_week: [4] }) }));
    // The workspace patches this row into local state instead of refetching
    // the whole list, so the response must carry the updated transaction.
    const body = await response.json();
    expect(body.transaction).toMatchObject({ id: 21, category: expect.objectContaining({ id: 4, name: "Groceries" }) });
  });

  it("forwards exact split lines and duplicate merge identifiers", async () => {
    apiPatch.mockResolvedValue(ok({ ...transaction(), splits: [{ id: 1, category: category(), amount: 30, notes: null }, { id: 2, category: { ...category(), id: 5, name: "Household" }, amount: 33.45, notes: null }] }));
    const split = await updateSplits(new Request("http://localhost/api/transactions/21/splits", { method: "PATCH", headers: { "content-type": "application/json" }, body: JSON.stringify({ clearSplits: false, splits: [{ categoryId: 4, amount: 30, notes: null }, { categoryId: 5, amount: 33.45, notes: null }] }) }), { params: Promise.resolve({ transactionId: "21" }) });
    expect(split.status).toBe(200);
    expect(apiPatch).toHaveBeenCalledWith("/v1/transactions/{transaction_id}/splits", expect.objectContaining({ body: { clear_splits: false, splits: [{ category_id: 4, amount: 30, notes: null }, { category_id: 5, amount: 33.45, notes: null }] } }));
    apiPost.mockResolvedValue(ok({ merged: true, surviving_transaction: transaction(), deleted_transaction_id: 22 }));
    await mergeDuplicates(new Request("http://localhost/api/transactions/duplicates/merge", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ firstTransactionId: 21, secondTransactionId: 22 }) }));
    expect(apiPost).toHaveBeenCalledWith("/v1/transactions/duplicates/merge", expect.objectContaining({ body: { first_transaction_id: 21, second_transaction_id: 22 } }));
  });

  it("maps the inferred CSV preview and preserves explicit debit-credit columns", async () => {
    apiPost.mockResolvedValue(ok({ staged_import_id: "stage-1", headers: ["Date", "Memo", "Debit", "Credit"], sample_rows: [{ Date: "07/18/2026", Memo: "Market", Debit: "63.45", Credit: "" }], mapping: { date: "Date", description: "Memo", amount: null, debit: "Debit", credit: "Credit", account: null }, new_transactions: [{ posted_date: "2026-07-18", description: "Market", amount: -63.45, transaction_type: "expense", source_name: "Imported Account", category_id: null, category_name: null }], new_count: 1, duplicate_count: 0 }));
    const response = await previewImport(new Request("http://localhost/api/transaction-imports/preview", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ csvText: "Date,Memo,Debit,Credit", fallbackAccount: "Imported Account", mapping: { date: "Date", description: "Memo", amount: null, debit: "Debit", credit: "Credit", account: null } }) }));
    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({ stagedImportId: "stage-1", mapping: { debit: "Debit", credit: "Credit" }, newTransactions: [{ amount: -63.45 }] });
  });
});
