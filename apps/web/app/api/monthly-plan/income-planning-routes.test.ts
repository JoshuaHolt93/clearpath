import { beforeEach, describe, expect, it, vi } from "vitest";

import { PATCH as updateRecurring } from "../recurring-templates/[templateId]/route";
import { POST as createRecurring } from "../recurring-templates/route";
import { PATCH as saveBaseline } from "./baseline/route";
import { GET } from "./route";

const apiGet = vi.hoisted(() => vi.fn());
const apiPost = vi.hoisted(() => vi.fn());
const apiPatch = vi.hoisted(() => vi.fn());

vi.mock("@clearpath/api-client", () => ({
  createClearPathClient: () => ({ GET: apiGet, POST: apiPost, PATCH: apiPatch, DELETE: vi.fn() }),
}));

function ok(data: unknown, status = 200) {
  return { data, error: undefined, response: new Response(null, { status }) };
}

function meResponse() {
  return {
    id: 1, household_name: "Parker Household", selected_plan: "premium", billing_status: "active",
    plan_display_name: "Premier", primary_account_holder: true,
    session_subject: { id: 1, subject_type: "user", email: "parker@example.com", display_name: "Parker User", first_name: "Parker", avatar_initial: "P", household_role: null },
    feature_access: [{ feature: "income_planning", enabled: true, hidden: false, required_plan: "Premier" }],
  };
}

function incomePlanResponse() {
  return {
    today: "2026-07-17",
    profile: {
      household_name: "Parker Household", income_amount: 90000, income_amount_display: 90000,
      monthly_income: 7600, income_basis: "gross", income_type: "salary", income_frequency: "semimonthly",
      paycheck_cadence: "semimonthly", next_pay_date: "2026-07-20", paycheck_second_date: "2026-07-31",
      paycheck_days_of_week: null, paycheck_second_day_of_month: 31, paycheck_monthly_week_numbers: null,
      paycheck_monthly_weekday: null, hourly_hours_per_week: 40, additional_income_amount: 1200,
      additional_income_frequency: "annual", tax_state: "NC", tax_filing_status: "married_joint",
      tax_additional_label: "County Tax", tax_additional_type: "percent", tax_additional_rate: 1.25,
      tax_additional_monthly_amount: 0, include_payroll_taxes: true, notes: "Summer plan",
    },
    plan: { income: 7600 },
    future_income_templates: [{
      id: 21, name: "Fall Raise", amount: 96000, item_type: "income", frequency: "semimonthly",
      start_date: "2026-09-01", second_date: "2026-09-30", days_of_week: null, second_day_of_month: 30,
      monthly_week_numbers: null, monthly_weekday: null, category_label: "Income", notes: "Promotion",
      income_replacement: true, income_basis: "gross", income_type: "salary", paycheck_cadence: "semimonthly",
      income_next_pay_date: "2026-09-15", hourly_hours_per_week: 40, additional_income_amount: 0,
      additional_income_frequency: "annual", tax_state: "NC", tax_filing_status: "married_joint",
      include_payroll_taxes: true, monthly_amount: 8000,
    }],
    tax_estimate: {
      annual_gross_income: 91200, taxable_income: 61200, federal_income_tax: 7000, state_income_tax: 3200,
      social_security_tax: 5654.4, medicare_tax: 1322.4, additional_medicare_tax: 0,
      additional_tax_label: "County Tax", additional_tax_type: "percent", additional_tax_rate: 1.25,
      additional_tax_annual: 1140, additional_tax_monthly: 95, annual_total: 18316.8, monthly_total: 1526.4,
      filing_status: "married_joint", state: "NC", state_rate: 4.5, state_method: "Progressive",
      state_taxable_income: 66000, state_standard_deduction: 25500, state_personal_exemption: 0,
      state_credit: 0, state_brackets: [[0, 0.045]], state_note: "North Carolina estimate.",
      state_source_url: "https://www.ncdor.gov/", federal_brackets: [[0, 23850, 0, 0.1], [23850, null, 2385, 0.12]],
      standard_deduction: 30000,
    },
    taxes_enabled: true,
    income_type_options: { salary: "Salary", hourly: "Hourly", bonus: "Bonus" },
    income_basis_options: { take_home: "Take-Home Income", gross: "Gross Income" },
    paycheck_cadence_options: { monthly: "Monthly", semimonthly: "Twice Per Month" },
    tax_filing_status_options: { married_joint: "Married Filing Jointly" }, state_options: { NC: "North Carolina" },
    recurring_frequency_options: { monthly: "Monthly", annual: "Annual" }, weekday_options: { 0: "Monday" },
    monthly_week_options: { 1: "First" },
  };
}

const headers = { "content-type": "application/json", cookie: "clearpath_session=full" };
const request = (url: string, method: string, body: unknown) => new Request(url, { method, headers, body: JSON.stringify(body) });

describe("Income Planning BFF routes", () => {
  beforeEach(() => { apiGet.mockReset(); apiPost.mockReset(); apiPatch.mockReset(); });

  it("maps the gated baseline resource without a GET-time Plaid side effect", async () => {
    apiGet.mockImplementation((path: string) => Promise.resolve(ok(path === "/v1/monthly-plan" ? incomePlanResponse() : meResponse())));
    const response = await GET(new Request("http://localhost/api/monthly-plan?section=baseline", { headers: { cookie: "clearpath_session=full" } }));
    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({
      profile: { paycheckCadence: "semimonthly", taxAdditionalLabel: "County Tax" },
      planIncome: 7600,
      futureIncomeTemplates: [{ id: 21, incomeReplacement: true, incomeNextPayDate: "2026-09-15" }],
      taxEstimate: { monthlyTotal: 1526.4, state: "NC", federalBrackets: [[0, 23850, 0, 0.1], [23850, null, 2385, 0.12]] },
    });
    expect(apiGet).toHaveBeenCalledWith("/v1/monthly-plan", expect.objectContaining({ params: { query: { view: "month", section: "baseline", budget_view: "list", budget_sort: "custom", quick_sort: "amount_desc", budget_month: "" } } }));
    expect(apiPost).not.toHaveBeenCalled();
  });

  it("forwards full baseline, tax worksheet, and future-income fields", async () => {
    apiPatch.mockImplementation((path: string) => Promise.resolve(path === "/v1/monthly-plan/baseline" ? ok({ profile: { household_name: "Parker Household" }, plan: { income: 7600 } }) : ok({ id: 21, name: "Fall Raise", monthly_amount: 8000 })));
    apiPost.mockResolvedValue(ok({ id: 21, name: "Fall Raise", monthly_amount: 8000 }, 201));

    const baseline = { householdName: "Parker Household", incomeAmount: 90000, incomeBasis: "gross", incomeType: "salary", paycheckCadence: "semimonthly", nextPayDate: "2026-07-20", secondDate: "2026-07-31", recurringDaysOfWeek: [], recurringMonthlyWeekNumbers: [], recurringMonthlyWeekday: null, hourlyHoursPerWeek: 40, additionalIncomeAmount: 1200, additionalIncomeFrequency: "annual", taxState: "NC", taxFilingStatus: "married_joint", includePayrollTaxes: true, notes: "Summer plan", view: "month", section: "baseline" };
    expect((await saveBaseline(request("http://local/api/monthly-plan/baseline", "PATCH", baseline))).status).toBe(200);
    expect((await saveBaseline(request("http://local/api/monthly-plan/baseline", "PATCH", { baselineScope: "core", taxAdditionalLabel: "County Tax", taxAdditionalType: "percent", taxAdditionalRate: 1.25, taxAdditionalMonthlyAmount: 0, view: "month", section: "baseline" }))).status).toBe(200);

    const future = { name: "Fall Raise", amount: 96000, itemType: "income", frequency: "semimonthly", startDate: "2026-09-01", secondDate: "2026-09-30", recurringDaysOfWeek: [], recurringMonthlyWeekNumbers: [], recurringMonthlyWeekday: null, categoryLabel: "Income", notes: "Promotion", incomeAdjustment: true, incomeReplacement: true, incomeBasis: "gross", incomeType: "salary", paycheckCadence: "semimonthly", incomeNextPayDate: "2026-09-15", incomeAmount: 96000, hourlyHoursPerWeek: 40, additionalIncomeAmount: 0, additionalIncomeFrequency: "annual", taxState: "NC", taxFilingStatus: "married_joint", includePayrollTaxes: true };
    expect((await createRecurring(request("http://local/api/recurring-templates", "POST", future))).status).toBe(201);
    expect((await updateRecurring(request("http://local/api/recurring-templates/21", "PATCH", future), { params: Promise.resolve({ templateId: "21" }) })).status).toBe(200);

    expect(apiPatch).toHaveBeenCalledWith("/v1/monthly-plan/baseline", expect.objectContaining({ body: expect.objectContaining({ baseline_scope: undefined, section: "baseline", income_amount: 90000 }) }));
    expect(apiPatch).toHaveBeenCalledWith("/v1/monthly-plan/baseline", expect.objectContaining({ body: expect.objectContaining({ baseline_scope: "core", tax_additional_label: "County Tax", tax_additional_rate: 1.25 }) }));
    expect(apiPost).toHaveBeenCalledWith("/v1/recurring-templates", expect.objectContaining({ body: expect.objectContaining({ income_adjustment: true, income_replacement: true, income_amount: 96000, paycheck_cadence: "semimonthly", income_next_pay_date: "2026-09-15" }) }));
    expect(apiPatch).toHaveBeenCalledWith("/v1/recurring-templates/{template_id}", expect.objectContaining({ body: expect.objectContaining({ income_basis: "gross", tax_state: "NC", include_payroll_taxes: true }) }));
  });
});
