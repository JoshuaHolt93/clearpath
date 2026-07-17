import { beforeEach, describe, expect, it, vi } from "vitest";

import { PATCH as saveAccountRole } from "../accounts/[accountId]/cash-projection-role/route";
import { DELETE as deleteFixed, PATCH as updateFixed } from "../fixed-expenses/[itemId]/route";
import { POST as createFixed } from "../fixed-expenses/route";
import { DELETE as deleteForecast, PATCH as updateForecast } from "../forecast-items/[itemId]/route";
import { POST as createForecast } from "../forecast-items/route";
import { DELETE as deleteRecurring, PATCH as updateRecurring } from "../recurring-templates/[templateId]/route";
import { POST as createRecurring } from "../recurring-templates/route";
import { DELETE as deleteVariable, PATCH as updateVariable } from "../variable-expenses/[itemId]/route";
import { POST as createVariable } from "../variable-expenses/route";
import { PATCH as saveBaseline } from "./baseline/route";
import { GET } from "./route";

const apiGet = vi.hoisted(() => vi.fn());
const apiPost = vi.hoisted(() => vi.fn());
const apiPatch = vi.hoisted(() => vi.fn());
const apiDelete = vi.hoisted(() => vi.fn());

vi.mock("@clearpath/api-client", () => ({
  createClearPathClient: () => ({ GET: apiGet, POST: apiPost, PATCH: apiPatch, DELETE: apiDelete }),
}));

function ok(data: unknown, status = 200) {
  return { data, error: undefined, response: new Response(null, { status }) };
}

function meResponse() {
  return {
    id: 1, household_name: "Parker Household", selected_plan: "premium", billing_status: "active",
    plan_display_name: "Premier", primary_account_holder: true,
    session_subject: { id: 1, subject_type: "user", email: "parker@example.com", display_name: "Parker User", first_name: "Parker", avatar_initial: "P", household_role: null },
    feature_access: [{ feature: "cash_projection", enabled: true, hidden: false, required_plan: "Premier" }],
  };
}

function quickPlanResponse() {
  return {
    month_name: "July 2026", today: "2026-07-17", quick_sort: "timing_asc",
    quick_sort_options: { timing_asc: "Soonest First" }, total_budget_planned: 1400,
    fixed_total: 1200, variable_plan_total: 650, quick_cash_remaining_income: 2500,
    quick_cash_remaining_expenses: 1675, quick_cash_week_change: -250, quick_cash_week_end_balance: 1750,
    quick_cash_projection: {
      end_date: "2026-07-31", end_balance: 2825,
      balance_anchor: { balance: 2000, checking_balance: 1800, account_count: 2, checking_account_count: 1, uses_cash_accounts: true, included_accounts: [{ id: 7, name: "Household Checking", institution: "Clear Bank", account_type: "checking", balance: 1800, mask: "1234", cash_projection_role: "auto" }] },
      lowest_balance: { date: "2026-07-24", balance: 950 },
    },
    cash_projection_account_rows: [{ account_id: 7, name: "Household Checking", institution: "Clear Bank", account_type: "checking", balance: 1800, mask: "1234", role: "auto", included: true, status_label: "Included", status_class: "badge-green", status_detail: "Automatically included" }],
    quick_worksheet_rows: [{ name: "Rent", subtitle: "Fixed expense", timing: "Jul 20", category: "Housing", amount: 1200, action_label: "Edit", readonly: false, item_type: "fixed_expense", item_id: 11 }],
    fixed_items: [{ id: 11, name: "Rent", amount: 1200, due_day: 20, start_date: "2026-07-20", frequency: "monthly", days_of_week: null, second_date: null, second_day_of_month: null, monthly_week_numbers: null, monthly_weekday: null, category_label: "Housing", is_loan: false, notes: null, monthly_amount: 1200 }],
    variable_items: [{ id: 12, name: "Groceries", amount: 150, frequency: "weekly", use_specific_date: false, specific_date: null, days_of_week: null, category_label: "Groceries", notes: null, monthly_amount: 650 }],
    forecast_items: [{ id: 13, item_date: "2026-07-28", description: "Repair", amount: 250, item_type: "expense", category_label: "Home", notes: null }],
    recurring_templates: [{ id: 14, name: "Gym", amount: 50, item_type: "expense", frequency: "monthly", start_date: "2026-07-22", second_date: null, days_of_week: null, second_day_of_month: null, monthly_week_numbers: null, monthly_weekday: null, category_label: "Health", notes: null, income_replacement: false, income_basis: null, income_type: null, paycheck_cadence: null, income_next_pay_date: null, hourly_hours_per_week: 0, additional_income_amount: 0, additional_income_frequency: "annual", tax_state: null, tax_filing_status: null, include_payroll_taxes: false, monthly_amount: 50 }],
    category_label_options: ["Housing", "Groceries", "Home", "Health"],
    profile: { household_name: "Parker Household", income_amount: 90000, income_amount_display: 90000, monthly_income: 6000, income_basis: "gross", income_type: "salary", income_frequency: "semimonthly", paycheck_cadence: "semimonthly", next_pay_date: "2026-07-20", paycheck_second_date: "2026-07-31", paycheck_days_of_week: null, paycheck_second_day_of_month: 31, paycheck_monthly_week_numbers: null, paycheck_monthly_weekday: null, hourly_hours_per_week: 40, additional_income_amount: 0, additional_income_frequency: "annual", tax_state: "NC", tax_filing_status: "married_joint", include_payroll_taxes: true, notes: "Summer plan" },
    plan: { income: 6000 }, income_type_options: { salary: "Salary" }, income_basis_options: { gross: "Gross" }, paycheck_cadence_options: { semimonthly: "Twice Per Month" }, tax_filing_status_options: { married_joint: "Married Filing Jointly" }, state_options: { NC: "North Carolina" }, recurring_frequency_options: { monthly: "Monthly", weekly: "Weekly" }, weekday_options: { 0: "Monday" }, monthly_week_options: { 1: "First" },
  };
}

const headers = { "content-type": "application/json", cookie: "clearpath_session=full" };
const request = (url: string, method: string, body: unknown) => new Request(url, { method, headers, body: JSON.stringify(body) });

describe("Quick Planning BFF routes", () => {
  beforeEach(() => { apiGet.mockReset(); apiPost.mockReset(); apiPatch.mockReset(); apiDelete.mockReset(); });

  it("maps the Quick Planning resource and forwards sort state without a read-time refresh", async () => {
    apiGet.mockImplementation((path: string) => Promise.resolve(ok(path === "/v1/monthly-plan" ? quickPlanResponse() : meResponse())));
    const response = await GET(new Request("http://localhost/api/monthly-plan?section=tools&quick_sort=timing_asc", { headers: { cookie: "clearpath_session=full" } }));
    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({ quickSort: "timing_asc", quickCashWeekChange: -250, quickCashProjection: { endBalance: 2825, balanceAnchor: { includedAccounts: [{ name: "Household Checking" }] } }, quickWorksheetRows: [{ itemType: "fixed_expense", itemId: 11 }], profile: { paycheckCadence: "semimonthly" } });
    expect(apiGet).toHaveBeenCalledWith("/v1/monthly-plan", expect.objectContaining({ params: { query: { view: "month", section: "tools", budget_view: "list", budget_sort: "custom", quick_sort: "timing_asc", budget_month: "" } } }));
    expect(apiPost).not.toHaveBeenCalled();
  });

  it("forwards create, full-edit, amount-only, delete, baseline, and account-role mutations", async () => {
    apiPost.mockImplementation((path: string) => Promise.resolve(path === "/v1/forecast-items" ? ok({ id: 13, description: "Repair", amount: 250 }, 201) : path === "/v1/recurring-templates" ? ok({ id: 14, name: "Gym", monthly_amount: 50 }, 201) : path === "/v1/variable-expenses" ? ok({ id: 12, name: "Groceries", monthly_amount: 650 }, 201) : ok({ id: 11, name: "Rent", monthly_amount: 1200 }, 201)));
    apiPatch.mockImplementation((path: string) => Promise.resolve(path === "/v1/monthly-plan/baseline" ? ok({ profile: { household_name: "Parker Home" }, plan: { income: 6200 } }) : path.includes("cash-projection-role") ? ok({ id: 7, cash_projection_role: "include" }) : path.includes("forecast-items") ? ok({ id: 13, description: "Roof Repair", amount: 300 }) : path.includes("recurring-templates") ? ok({ id: 14, name: "Gym", monthly_amount: 55 }) : path.includes("variable-expenses") ? ok({ id: 12, name: "Groceries", monthly_amount: 700 }) : ok({ id: 11, name: "Rent", monthly_amount: 1250 })));
    apiDelete.mockImplementation((path: string) => Promise.resolve(path.includes("recurring-templates") ? ok({ deleted_template_id: 14 }) : ok({ deleted_item_id: Number(path.includes("forecast") ? 13 : path.includes("variable") ? 12 : 11) })));

    const fixed = { name: "Rent", amount: 1200, frequency: "monthly", startDate: "2026-07-20", secondDate: null, daysOfWeek: [], recurringMonthlyWeekNumbers: [], recurringMonthlyWeekday: null, categoryLabel: "Housing", entryContext: null, notes: null };
    const variable = { name: "Groceries", amount: 150, frequency: "weekly", useSpecificDate: false, specificDate: null, daysOfWeek: [], categoryLabel: "Groceries", notes: null };
    const forecast = { itemDate: "2026-07-28", description: "Repair", amount: 250, itemType: "expense", categoryLabel: "Home", notes: null };
    const recurring = { name: "Gym", amount: 50, itemType: "expense", frequency: "monthly", startDate: "2026-07-22", secondDate: null, recurringDaysOfWeek: [], recurringMonthlyWeekNumbers: [], recurringMonthlyWeekday: null, categoryLabel: "Health", notes: null, incomeAdjustment: false };

    expect((await createFixed(request("http://local/api/fixed-expenses", "POST", fixed))).status).toBe(201);
    expect((await updateFixed(request("http://local/api/fixed-expenses/11", "PATCH", { monthlyTarget: 1250 }), { params: Promise.resolve({ itemId: "11" }) })).status).toBe(200);
    expect((await deleteFixed(request("http://local/api/fixed-expenses/11", "DELETE", { confirm: true }), { params: Promise.resolve({ itemId: "11" }) })).status).toBe(200);
    expect((await createVariable(request("http://local/api/variable-expenses", "POST", variable))).status).toBe(201);
    expect((await updateVariable(request("http://local/api/variable-expenses/12", "PATCH", { monthlyTarget: 700 }), { params: Promise.resolve({ itemId: "12" }) })).status).toBe(200);
    expect((await deleteVariable(request("http://local/api/variable-expenses/12", "DELETE", { confirm: true }), { params: Promise.resolve({ itemId: "12" }) })).status).toBe(200);
    expect((await createForecast(request("http://local/api/forecast-items", "POST", forecast))).status).toBe(201);
    expect((await updateForecast(request("http://local/api/forecast-items/13", "PATCH", { ...forecast, description: "Roof Repair", amount: 300 }), { params: Promise.resolve({ itemId: "13" }) })).status).toBe(200);
    expect((await deleteForecast(request("http://local/api/forecast-items/13", "DELETE", { confirm: true }), { params: Promise.resolve({ itemId: "13" }) })).status).toBe(200);
    expect((await createRecurring(request("http://local/api/recurring-templates", "POST", recurring))).status).toBe(201);
    expect((await updateRecurring(request("http://local/api/recurring-templates/14", "PATCH", { monthlyTarget: 55 }), { params: Promise.resolve({ templateId: "14" }) })).status).toBe(200);
    expect((await deleteRecurring(request("http://local/api/recurring-templates/14", "DELETE", { confirm: true }), { params: Promise.resolve({ templateId: "14" }) })).status).toBe(200);
    expect((await saveBaseline(request("http://local/api/monthly-plan/baseline", "PATCH", { baselineScope: "core", householdName: "Parker Home", incomeAmount: 90000, incomeBasis: "gross", incomeType: "salary", paycheckCadence: "monthly", recurringDaysOfWeek: [], recurringMonthlyWeekNumbers: [], includePayrollTaxes: true, view: "month", section: "tools" }))).status).toBe(200);
    expect((await saveAccountRole(request("http://local/api/accounts/7/cash-projection-role", "PATCH", { cashProjectionRole: "include" }), { params: Promise.resolve({ accountId: "7" }) })).status).toBe(200);

    expect(apiPatch).toHaveBeenCalledWith("/v1/fixed-expenses/{item_id}", expect.objectContaining({ body: expect.objectContaining({ monthly_target: 1250, name: "", frequency: "monthly" }) }));
    expect(apiPatch).toHaveBeenCalledWith("/v1/monthly-plan/baseline", expect.objectContaining({ body: expect.objectContaining({ household_name: "Parker Home", baseline_scope: "core" }) }));
    expect(apiPatch).toHaveBeenCalledWith("/v1/accounts/{account_id}/cash-projection-role", expect.objectContaining({ body: { cash_projection_role: "include" } }));
  });
});
