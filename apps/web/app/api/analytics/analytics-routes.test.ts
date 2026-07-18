import { beforeEach, describe, expect, it, vi } from "vitest";

import { GET } from "./route";

const apiGet = vi.hoisted(() => vi.fn());
vi.mock("@clearpath/api-client", () => ({ createClearPathClient: () => ({ GET: apiGet }) }));

function subscription() {
  return { id: 8, name: "Stream Box", service_category: "Streaming", monthly_amount: 20, annual_amount: 240, cycle: "Monthly", confidence: .9, status: "active", replaceable: true, next_charge_date: "2026-07-28" };
}

function summary(rangeKey = "month") {
  return {
    range_key: rangeKey, range_label: rangeKey === "month" ? "Month" : "Quarter", months: ["2026-07-01"], start_date: "2026-07-01", end_date: "2026-07-31",
    snapshots: [{ month: "2026-07-01", planned_income: 5000, planned_fixed_expenses: 1800, planned_variable_expenses: 800, planned_savings: 400, planned_debt_payment: 250, planned_taxes: 700, planned_retirement: 300, planned_safe_to_spend: 800, expected_cash_flow: 1700, budget_remaining: 500, actual_income: 4900, actual_fixed_expenses: 1750, actual_variable_expenses: 725, actual_total_expenses: 2475, net_cash_flow: 2425 }],
    total_income: 4900, total_spending: 2475, total_expected_cash_flow: 1700, total_net_cash_flow: 2425, average_income: 4900, average_spending: 2475, average_net_cash_flow: 2425, max_income: 5000, max_spending: 3300, max_cash_flow: 2425,
    category_rows: [{ category: "Groceries", category_id: 3, amount: 425 }],
    subscriptions: { subscriptions: [subscription()], active_count: 1, review_count: 0, action_count: 1, manage_link_count: 0, monthly_total: 20, annual_total: 240, potential_savings: 20, spending_share: 1, category_breakdown: [{ category: "Streaming", amount: 20, percent: 100 }], opportunities: [{ subscription: subscription(), reason: "Replaceable service" }], upcoming: [subscription()] },
  };
}

function analyticsResponse() {
  return { summary: summary(), budget_history_summary: summary("quarter"), debt_to_income_ratio: .32, range_options: { month: "Month", quarter: "Quarter", six_months: "6 Months", year: "1 Year" }, selected_range: "month", end_month: "2026-07-01", selected_history_range: "quarter", history_end_month: "2026-07-01", subscription_analytics_enabled: true, subscription_analytics_plan_label: "Plus", ai_coach_enabled: true, ai_coach_hidden: false };
}

function meResponse() {
  return { id: 1, email: "owner@example.com", display_name: "Owner", household_name: "Owner Home", selected_plan: "premium", billing_status: "active", is_admin: false, session_subject: { id: 1, subject_type: "user", email: "owner@example.com", display_name: "Owner", first_name: "Owner", avatar_initial: "O", household_role: null }, primary_account_holder: true, plan_display_name: "Premier", feature_access: [] };
}

describe("analytics BFF route", () => {
  beforeEach(() => apiGet.mockReset());

  it("forwards independent analytics ranges and maps the typed response", async () => {
    apiGet.mockImplementation((path: string) => Promise.resolve({ data: path === "/v1/analytics" ? analyticsResponse() : meResponse(), error: undefined, response: new Response(null, { status: 200 }) }));
    const response = await GET(new Request("http://localhost/api/analytics?range=year&end_month=2026-06&history_range=six_months&history_end_month=2026-05", { headers: { cookie: "clearpath_session=full" } }));
    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({ session: { primaryAccountHolder: true }, summary: { totalIncome: 4900, subscriptions: { monthlyTotal: 20 } }, budgetHistorySummary: { rangeKey: "quarter" }, debtToIncomeRatio: .32 });
    expect(apiGet).toHaveBeenCalledWith("/v1/analytics", { headers: { cookie: "clearpath_session=full" }, params: { query: { range: "year", end_month: "2026-06", history_range: "six_months", history_end_month: "2026-05" } } });
    expect(apiGet).toHaveBeenCalledWith("/v1/me", { headers: { cookie: "clearpath_session=full" } });
    expect(response.headers.get("cache-control")).toBe("no-store");
  });

  it("returns the upstream analytics error", async () => {
    apiGet.mockImplementation((path: string) => Promise.resolve(path === "/v1/analytics" ? { data: undefined, error: { detail: "Onboarding required" }, response: new Response(null, { status: 409 }) } : { data: meResponse(), error: undefined, response: new Response(null, { status: 200 }) }));
    const response = await GET(new Request("http://localhost/api/analytics"));
    expect(response.status).toBe(409);
    expect(await response.json()).toMatchObject({ message: "Onboarding required" });
  });
});
