import { beforeEach, describe, expect, it, vi } from "vitest";

import { DELETE as deleteBudget, PATCH as updateBudget } from "../budgets/[categoryId]/route";
import { POST as startLoanPlan } from "../budgets/[categoryId]/loan-plan/route";
import { PATCH as saveLayout } from "../budgets/layout/route";
import { POST as createBudget } from "../budgets/route";
import { GET } from "./route";

const apiGet = vi.hoisted(() => vi.fn());
const apiPost = vi.hoisted(() => vi.fn());
const apiPatch = vi.hoisted(() => vi.fn());
const apiDelete = vi.hoisted(() => vi.fn());

vi.mock("@clearpath/api-client", () => ({
  createClearPathClient: () => ({ GET: apiGet, POST: apiPost, PATCH: apiPatch, DELETE: apiDelete }),
}));

function meResponse() {
  return {
    id: 1,
    email: "owner@example.com",
    display_name: "Owner",
    household_name: "Owner Home",
    selected_plan: "basic",
    billing_status: "free",
    is_admin: false,
    session_subject: { id: 1, subject_type: "user", email: "owner@example.com", display_name: "Owner User", first_name: "Owner", avatar_initial: "O", household_role: null },
    primary_account_holder: true,
    plan_display_name: "Plus",
    feature_access: [{ feature: "subscriptions", enabled: true, hidden: false, required_plan: "Plus" }],
  };
}

function budgetRow(overrides: Record<string, unknown> = {}) {
  return {
    kind: "category",
    category_kind: "expense",
    category_id: 3,
    label: "Groceries",
    category: "Groceries",
    group_key: "daily_living",
    planned: 600,
    actual: 250,
    remaining: 350,
    progress_percent: 41.6667,
    progress_status: "ok",
    anchor_id: "budget-groceries",
    transaction_ids: [8],
    transaction_count: 1,
    suggestion_match_count: 0,
    sort_order: 1,
    can_remove_budget: true,
    amortization_action: null,
    actual_label: "spent",
    planned_label: "planned",
    adjust_label: "",
    ...overrides,
  };
}

function planResponse() {
  return {
    month_name: "July 2026",
    today: "2026-07-17",
    budget_view: "grouped",
    budget_grouped: true,
    budget_sort: "amount_desc",
    budget_drag_enabled: false,
    budget_selected_month: "2026-07-01",
    budget_current_month: "2026-07-01",
    budget_month_value: "2026-07",
    budget_month_label: "July 2026",
    budget_is_current_month: true,
    budget_history_mode: false,
    total_budget_planned: 600,
    total_budget_actual: 250,
    total_budget_remaining: 350,
    expected_cash_flow: 4650,
    budget_sections: [{ label: "Daily Living", kind: "daily_living", description: "Everyday household costs.", empty: "No category budgets.", rows: [budgetRow()], planned: 600, actual: 250, transaction_ids: [8], transaction_count: 1 }],
    suggested_budget_sections: [{ label: "Transportation", kind: "transportation", rows: [budgetRow({ category_id: 4, label: "Fuel/Gasoline", category: "Fuel/Gasoline", planned: 75, suggestion_match_count: 2 })] }],
    unassigned_budget_rows: [budgetRow({ kind: "cleanup", category_kind: "cleanup", category_id: null, label: "Other Spending To Categorize", category: "Other Spending To Categorize", planned: 0, actual: 40, remaining: -40, progress_percent: 100, progress_status: "over", anchor_id: "budget-cleanup", can_remove_budget: false })],
    category_label_options: ["Groceries", "Fuel/Gasoline"],
    budget_group_options: [{ key: "daily_living", label: "Daily Living", description: "Everyday household costs." }],
    budget_sort_options: { custom: "Custom Order", amount_desc: "Highest Budget First" },
  };
}

describe("monthly budget BFF routes", () => {
  beforeEach(() => {
    apiGet.mockReset();
    apiPost.mockReset();
    apiPatch.mockReset();
    apiDelete.mockReset();
  });

  it("maps grouped budget data and forwards the canonical read query without a refresh side effect", async () => {
    apiGet.mockImplementation((path: string) => Promise.resolve({ data: path === "/v1/monthly-plan" ? planResponse() : meResponse(), error: undefined, response: new Response(null, { status: 200 }) }));
    const response = await GET(new Request("http://localhost/api/monthly-plan?section=budgets&budget_view=grouped&budget_sort=amount_desc&onboarding=complete", { headers: { cookie: "clearpath_session=full" } }));
    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({
      onboardingComplete: true,
      budgetGrouped: true,
      totalBudgetRemaining: 350,
      session: { subject: { displayName: "Owner User" } },
      budgetSections: [{ rows: [{ categoryId: 3, transactionIds: [8], planned: 600 }] }],
      suggestedBudgetSections: [{ rows: [{ category: "Fuel/Gasoline", suggestionMatchCount: 2 }] }],
    });
    expect(apiGet).toHaveBeenCalledWith("/v1/monthly-plan", expect.objectContaining({ params: { query: { view: "month", section: "budgets", budget_view: "grouped", budget_sort: "amount_desc", quick_sort: "amount_desc", budget_month: "" } } }));
    expect(apiPost).not.toHaveBeenCalled();
  });

  it("forwards create, amount, layout, delete, and amortization mutations through typed resources", async () => {
    apiPost
      .mockResolvedValueOnce({ data: { category: { id: 3, name: "Groceries", monthly_target: 600 }, group_key: "daily_living", group_label: "Daily Living" }, error: undefined, response: new Response(null, { status: 201 }) })
      .mockResolvedValueOnce({ data: { fixed_expense: { id: 22 } }, error: undefined, response: new Response(null, { status: 200 }) });
    apiPatch
      .mockResolvedValueOnce({ data: { category: { id: 3, monthly_target: 650 } }, error: undefined, response: new Response(null, { status: 200 }) })
      .mockResolvedValueOnce({ data: { ok: true, updated: 2 }, error: undefined, response: new Response(null, { status: 200 }) });
    apiDelete.mockResolvedValue({ data: { deleted_category_id: 3, replacement_category: null }, error: undefined, response: new Response(null, { status: 200 }) });

    expect((await createBudget(new Request("http://localhost/api/budgets", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ categoryLabel: "Groceries", monthlyTarget: 600, categoryKind: "expense", budgetMonth: "2026-07" }) }))).status).toBe(201);
    expect((await updateBudget(new Request("http://localhost/api/budgets/3", { method: "PATCH", headers: { "content-type": "application/json" }, body: JSON.stringify({ monthlyTarget: 650, budgetMonth: "2026-07" }) }), { params: Promise.resolve({ categoryId: "3" }) })).status).toBe(200);
    expect((await saveLayout(new Request("http://localhost/api/budgets/layout", { method: "PATCH", headers: { "content-type": "application/json" }, body: JSON.stringify({ budgetMonth: "2026-07", rows: [{ categoryId: 3, groupKey: "daily_living" }, { categoryId: 4, groupKey: "transportation" }] }) }))).status).toBe(200);
    expect((await deleteBudget(new Request("http://localhost/api/budgets/3", { method: "DELETE", headers: { "content-type": "application/json" }, body: JSON.stringify({ budgetMonth: "2026-07" }) }), { params: Promise.resolve({ categoryId: "3" }) })).status).toBe(200);
    expect(await (await startLoanPlan(new Request("http://localhost/api/budgets/3/loan-plan", { method: "POST" }), { params: Promise.resolve({ categoryId: "3" }) })).json()).toEqual({ fixedExpenseItemId: 22 });

    expect(apiPatch).toHaveBeenCalledWith("/v1/budgets/{category_id}", expect.objectContaining({ params: { path: { category_id: 3 } }, body: { monthly_target: 650, budget_month: "2026-07" } }));
    expect(apiDelete).toHaveBeenCalledWith("/v1/budgets/{category_id}", expect.objectContaining({ body: { budget_month: "2026-07" } }));
  });
});
