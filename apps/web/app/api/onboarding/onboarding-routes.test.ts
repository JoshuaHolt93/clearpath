import { beforeEach, describe, expect, it, vi } from "vitest";

import { POST as linkToken } from "./plaid/link-token/route";
import { GET, PATCH, POST } from "./route";
import { PATCH as updateCategory } from "./transactions/[transactionId]/category/route";

const apiGet = vi.hoisted(() => vi.fn());
const apiPatch = vi.hoisted(() => vi.fn());
const apiPost = vi.hoisted(() => vi.fn());

vi.mock("@clearpath/api-client", () => ({
  createClearPathClient: () => ({ GET: apiGet, PATCH: apiPatch, POST: apiPost }),
}));

function apiStatus(overrides: Record<string, unknown> = {}) {
  return {
    active_step: "income",
    income_ready: false,
    has_bank: true,
    setup_complete: false,
    profile: {
      household_name: "Parker Household",
      income_amount: 0,
      income_amount_display: 0,
      monthly_income: 0,
      income_basis: "take_home",
      income_type: "salary",
      paycheck_cadence: "monthly",
      next_pay_date: "2026-07-31",
      paycheck_second_date: null,
      paycheck_days_of_week: null,
      paycheck_monthly_week_numbers: null,
      paycheck_monthly_weekday: null,
      hourly_hours_per_week: 40,
      additional_income_amount: 0,
      additional_income_frequency: "annual",
      tax_state: null,
      tax_filing_status: "married_joint",
      include_payroll_taxes: true,
      notes: null,
    },
    today: "2026-07-16",
    plaid_status: { ready: true, sdk_installed: true, crypto_installed: true, has_credentials: true, has_encryption_key: true, environment: "sandbox" },
    plaid_items: [{ id: 4, institution_name: "First Test Bank", status: "connected", last_synced_at: null }],
    transactions: [],
    categories: [{ id: 7, name: "Groceries", kind: "expense" }],
    auto_categorized_count: 0,
    seeded_budget_count: 0,
    message: null,
    next_path: null,
    income_basis_options: { take_home: "Take-Home", gross: "Gross" },
    income_type_options: { salary: "Salary", hourly: "Hourly" },
    paycheck_cadence_options: { monthly: "Monthly", semimonthly: "Twice Monthly" },
    recurring_frequency_options: { monthly: "Monthly", annual: "Annual" },
    weekday_options: { "0": "Monday" },
    monthly_week_options: { "1": "First" },
    tax_filing_status_options: { married_joint: "Married Filing Jointly" },
    state_options: { "": "Choose State", IN: "Indiana" },
    ...overrides,
  };
}

describe("onboarding BFF routes", () => {
  beforeEach(() => {
    apiGet.mockReset();
    apiPatch.mockReset();
    apiPost.mockReset();
  });

  it("forwards the full-session cookie and maps onboarding status", async () => {
    apiGet.mockResolvedValue({ data: apiStatus(), error: undefined, response: new Response(null, { status: 200 }) });
    const response = await GET(new Request("http://localhost/api/onboarding?step=income", {
      headers: { cookie: "clearpath_session=full-token" },
    }));
    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({ activeStep: "income", hasBank: true, profile: { householdName: "Parker Household" } });
    expect(apiGet).toHaveBeenCalledWith("/v1/onboarding/status", {
      params: { query: { step: "income" } },
      headers: { cookie: "clearpath_session=full-token" },
    });
  });

  it("validates and forwards the complete income plan", async () => {
    apiPatch.mockResolvedValue({ data: apiStatus({ active_step: "transactions", income_ready: true }), error: undefined, response: new Response(null, { status: 200 }) });
    const body = {
      income_amount: 120000,
      income_basis: "take_home",
      income_type: "salary",
      paycheck_cadence: "monthly",
      next_pay_date: "2026-07-31",
      second_date: null,
      recurring_days_of_week: [],
      recurring_monthly_week_numbers: [],
      recurring_monthly_weekday: null,
      hourly_hours_per_week: 40,
      fixed_expenses: 0,
      variable_expenses: 0,
      additional_income_amount: 0,
      additional_income_frequency: "annual",
      planned_savings_contribution: 0,
      planned_debt_payment: 0,
      target_investment_contribution: 0,
      tax_filing_status: "married_joint",
      tax_state: null,
      include_payroll_taxes: true,
      notes: "",
    };
    const response = await PATCH(new Request("http://localhost/api/onboarding", {
      method: "PATCH",
      headers: { "content-type": "application/json", cookie: "clearpath_session=full-token" },
      body: JSON.stringify(body),
    }));
    expect(response.status).toBe(200);
    expect(apiPatch).toHaveBeenCalledWith("/v1/onboarding/income-plan", {
      body,
      headers: { cookie: "clearpath_session=full-token" },
    });
  });

  it("surfaces structured completion gates from FastAPI", async () => {
    apiPost.mockResolvedValue({
      data: undefined,
      error: { detail: { code: "bank_connection_required", step: "connect", message: "Connect a bank account before finishing setup." } },
      response: new Response(null, { status: 409 }),
    });
    const response = await POST(new Request("http://localhost/api/onboarding", { method: "POST" }));
    expect(response.status).toBe(409);
    expect(await response.json()).toEqual({ message: "Connect a bank account before finishing setup." });
  });

  it("uses generated transaction defaults and maps Plaid Link tokens", async () => {
    apiPatch.mockResolvedValue({
      data: { transaction: { id: 12, category: { id: 7 } } },
      error: undefined,
      response: new Response(null, { status: 200 }),
    });
    const updated = await updateCategory(new Request("http://localhost", {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ category_id: 7 }),
    }), { params: Promise.resolve({ transactionId: "12" }) });
    expect(await updated.json()).toEqual({ transactionId: 12, categoryId: 7 });
    expect(apiPatch).toHaveBeenCalledWith("/v1/transactions/{transaction_id}/category", expect.objectContaining({
      body: { category_id: 7, apply_to_similar: false, mark_recurring: false, recurring_frequency: "monthly" },
    }));

    apiPost.mockResolvedValue({ data: { link_token: "link-token", consent_token: "consent-token" }, error: undefined, response: new Response(null, { status: 200 }) });
    const linked = await linkToken(new Request("http://localhost", { method: "POST" }));
    expect(await linked.json()).toEqual({ linkToken: "link-token", consentToken: "consent-token" });
  });
});
