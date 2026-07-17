import { beforeEach, describe, expect, it, vi } from "vitest";

import { DELETE as logout } from "../auth/session/route";
import { DELETE as deleteGoal } from "../goals/[goalId]/route";
import { POST as refreshPlaid } from "../plaid-items/refresh-stale/route";
import { GET } from "./route";

const apiGet = vi.hoisted(() => vi.fn());
const apiPost = vi.hoisted(() => vi.fn());
const apiDelete = vi.hoisted(() => vi.fn());

vi.mock("@clearpath/api-client", () => ({
  createClearPathClient: () => ({ GET: apiGet, POST: apiPost, DELETE: apiDelete }),
}));

function dashboardResponse() {
  return {
    metrics: {
      month_income: 5000,
      fixed_expenses: 1800,
      variable_spend: 200,
      safe_to_spend: 3000,
      safe_to_spend_target: 3200,
      net_cash_flow: 3000,
      on_track_status: "green",
      expected_variable_spend: 1600,
    },
    net_worth: {
      assets: 60000,
      liabilities: 105000,
      loan_balances: 100000,
      collateral_assets: 50000,
      collateral_value: 150000,
      secured_loan_equity: 50000,
      secured_negative_equity: 0,
      secured_loan_balances: 100000,
      unsecured_loan_balances: 0,
      debt_goals: 3000,
      net_worth: -45000,
    },
    category_totals: [{ category: "Groceries", category_id: 3, amount: 200 }],
    goals: [{
      goal: { id: 4, name: "Family Loan", goal_type: "debt", target_amount: 5000, current_amount: 2000, monthly_contribution: 100, target_date: "2027-01-31", fixed_expense_item_id: null },
      progress: 40,
      timeline: "30 months",
      remaining: 3000,
      current_amount: 2000,
      target_amount: 5000,
      required_monthly: 0,
      required_extra: 0,
      linked_item: null,
    }],
    recent_transactions: [{
      id: 7,
      posted_date: "2026-07-16",
      description: "Grocery Run",
      merchant: "Kroger",
      amount: -200,
      transaction_type: "expense",
      source_name: "Checking",
      import_hash: "hash",
      notes: null,
      plaid_transaction_id: null,
      plaid_metadata: null,
      pending: false,
      category: { id: 3, name: "Groceries", kind: "expense", monthly_target: 600, is_default: false, budget_group_key: null, budget_sort_order: null, can_manage: true },
      account: null,
      splits: [],
    }],
    accounts: [],
    month_name: "July 2026",
    today: "2026-07-16",
    elapsed_days: 16,
    total_days: 31,
    days_left: 15,
    pace_pct: 51.6,
    spend_pct: 6.3,
    feature_states: [],
    plan_rows: [{ label: "Expenses", planned: 2400, actual: 2000, type: "expense", details: [{ label: "Groceries", planned: 600, actual: 200, source: "transactions" }] }],
    budget_remaining: 400,
    expected_cash_flow: 2600,
    insights: [{ title: "Room to build savings", body: "Your plan has a surplus.", level: "good", type: "surplus_opportunity", disclaimer: "Educational guidance only." }],
    dashboard_focus: { items: [], generated_at: null, message: "Generate guidance to add a dashboard focus." },
  };
}

function meResponse() {
  return {
    id: 1,
    email: "owner@example.com",
    display_name: "Owner User",
    household_name: "Owner Home",
    selected_plan: "premium",
    billing_status: "active",
    is_admin: false,
    session_subject: { id: 9, subject_type: "household_member", email: "viewer@example.com", display_name: "Taylor Viewer", first_name: "Taylor", avatar_initial: "T", household_role: "viewer" },
    primary_account_holder: false,
    plan_display_name: "Premier",
    feature_access: [{ feature: "cash_projection", enabled: true, hidden: false, required_plan: "Plus" }],
  };
}

describe("dashboard BFF routes", () => {
  beforeEach(() => {
    apiGet.mockReset();
    apiPost.mockReset();
    apiDelete.mockReset();
  });

  it("combines typed dashboard and signed-in subject data without refreshing on GET", async () => {
    apiGet.mockImplementation((path: string) => Promise.resolve({
      data: path === "/v1/dashboard" ? dashboardResponse() : meResponse(),
      error: undefined,
      response: new Response(null, { status: 200 }),
    }));
    const response = await GET(new Request("http://localhost/api/dashboard?welcome=1", {
      headers: { cookie: "clearpath_session=full; clearpath_today_tutorial=1" },
    }));
    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({
      showTutorial: true,
      session: { subject: { displayName: "Taylor Viewer", householdRole: "viewer" }, primaryAccountHolder: false },
      metrics: { safeToSpend: 3000 },
      categoryTotals: [{ category: "Groceries", categoryId: 3, amount: 200 }],
      planRows: [{ label: "Expenses", details: [{ label: "Groceries", actual: 200 }] }],
    });
    expect(apiGet).toHaveBeenCalledTimes(2);
    expect(apiGet).toHaveBeenCalledWith("/v1/dashboard", { headers: { cookie: "clearpath_session=full; clearpath_today_tutorial=1" } });
    expect(apiPost).not.toHaveBeenCalled();
    expect(response.headers.get("set-cookie")).toContain("clearpath_today_tutorial=");
    expect(response.headers.get("set-cookie")).toContain("Max-Age=0");
  });

  it("uses the explicit throttled Plaid refresh mutation", async () => {
    apiPost.mockResolvedValue({ data: { synced: 1, errors: [] }, error: undefined, response: new Response(null, { status: 200 }) });
    const response = await refreshPlaid(new Request("http://localhost/api/plaid-items/refresh-stale", {
      method: "POST",
      headers: { cookie: "clearpath_session=full" },
    }));
    expect(await response.json()).toEqual({ synced: 1, errors: [] });
    expect(apiPost).toHaveBeenCalledWith("/v1/plaid-items/refresh-stale", {
      body: {},
      headers: { cookie: "clearpath_session=full" },
    });
  });

  it("forwards the API cookie deletion when signing out", async () => {
    apiDelete.mockResolvedValue({
      data: { ok: true },
      error: undefined,
      response: new Response(null, { status: 200, headers: { "set-cookie": "clearpath_session=; Path=/; Max-Age=0" } }),
    });
    const response = await logout(new Request("http://localhost/api/auth/session", {
      method: "DELETE",
      headers: { cookie: "clearpath_session=full" },
    }));
    expect(await response.json()).toEqual({ ok: true });
    expect(response.headers.get("set-cookie")).toContain("clearpath_session=");
  });

  it("deletes a dashboard goal through the existing typed resource", async () => {
    apiDelete.mockResolvedValue({
      data: { deleted_goal_id: 4 },
      error: undefined,
      response: new Response(null, { status: 200 }),
    });
    const response = await deleteGoal(
      new Request("http://localhost/api/goals/4", { method: "DELETE", headers: { cookie: "clearpath_session=full" } }),
      { params: Promise.resolve({ goalId: "4" }) },
    );
    expect(await response.json()).toEqual({ deletedGoalId: 4 });
    expect(apiDelete).toHaveBeenCalledWith("/v1/goals/{goal_id}", {
      params: { path: { goal_id: 4 } },
      body: { confirm: true },
      headers: { cookie: "clearpath_session=full" },
    });
  });
});
