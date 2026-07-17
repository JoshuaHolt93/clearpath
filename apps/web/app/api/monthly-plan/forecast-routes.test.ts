import { beforeEach, describe, expect, it, vi } from "vitest";

import { GET } from "./route";

const apiGet = vi.hoisted(() => vi.fn());
const apiPost = vi.hoisted(() => vi.fn());

vi.mock("@clearpath/api-client", () => ({
  createClearPathClient: () => ({ GET: apiGet, POST: apiPost }),
}));

function ok(data: unknown) {
  return { data, error: undefined, response: new Response(null, { status: 200 }) };
}

function meResponse() {
  return {
    id: 1,
    household_name: "Parker Household",
    selected_plan: "premium",
    billing_status: "active",
    plan_display_name: "Premier",
    primary_account_holder: true,
    session_subject: { id: 1, subject_type: "user", email: "parker@example.com", display_name: "Parker User", first_name: "Parker", avatar_initial: "P", household_role: null },
    feature_access: [{ feature: "cash_projection", enabled: true, hidden: false, required_plan: "Premier" }],
  };
}

function forecastMonth(monthStart: string, monthName: string, plannedBuffer: number, endingCash: number) {
  return {
    month_start: monthStart,
    month_name: monthName,
    baseline_income: 4000,
    fixed_expenses: 1100,
    planned_savings: 300,
    planned_debt: 200,
    planned_taxes: 500,
    planned_retirement: 200,
    planned_variable: 700,
    planned_income: 400,
    planned_expenses: 600,
    one_time_income: 400,
    one_time_expenses: 600,
    forecast_income_total: 4800,
    forecast_expense_total: 3600,
    planned_buffer: plannedBuffer,
    starting_cash: 2500,
    ending_cash: endingCash,
    forecast_items: [{ date: monthStart, description: "Tax refund", amount: 400, item_type: "income", source: "one_time", source_id: 31, category_label: "Income", notes: null, pending: false, signed_amount: 400, account_name: null }],
  };
}

function forecastPlanResponse() {
  return {
    today: "2026-07-17",
    forecast_months: [
      forecastMonth("2026-07-01", "July 2026", 1200, 3700),
      forecastMonth("2026-08-01", "August 2026", 250, 3950),
      forecastMonth("2026-09-01", "September 2026", -50, 3900),
    ],
    forecast_items: [
      { id: 31, item_date: "2026-07-20", description: "Tax refund", amount: 400, item_type: "income", category_label: "Income", notes: null },
      { id: 32, item_date: "2026-07-28", description: "Car repair", amount: 600, item_type: "expense", category_label: "Auto", notes: "Expected quote" },
    ],
    category_label_options: ["Auto", "Income"],
  };
}

describe("3-Month Forecast BFF", () => {
  beforeEach(() => { apiGet.mockReset(); apiPost.mockReset(); });

  it("maps the forecast-only monthly-plan payload without triggering refresh as a GET side effect", async () => {
    apiGet.mockImplementation((path: string) => Promise.resolve(ok(path === "/v1/monthly-plan" ? forecastPlanResponse() : meResponse())));

    const response = await GET(new Request("http://localhost/api/monthly-plan?section=forecast", { headers: { cookie: "clearpath_session=full" } }));

    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({
      today: "2026-07-17",
      forecastMonths: [
        { monthName: "July 2026", plannedBuffer: 1200, endingCash: 3700, forecastItems: [{ description: "Tax refund", itemType: "income", sourceId: 31 }] },
        { monthName: "August 2026", plannedBuffer: 250 },
        { monthName: "September 2026", plannedBuffer: -50 },
      ],
      forecastItems: [{ id: 31, itemType: "income" }, { id: 32, itemType: "expense", notes: "Expected quote" }],
      categoryLabelOptions: ["Auto", "Income"],
    });
    expect(apiGet).toHaveBeenCalledWith("/v1/monthly-plan", expect.objectContaining({
      params: { query: { view: "month", section: "forecast", budget_view: "list", budget_sort: "custom", quick_sort: "amount_desc", budget_month: "" } },
    }));
    expect(apiPost).not.toHaveBeenCalled();
  });
});
