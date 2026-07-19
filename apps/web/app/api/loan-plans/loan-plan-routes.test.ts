import { beforeEach, describe, expect, it, vi } from "vitest";

import { GET as getDetail, PATCH as updateDetail } from "./[itemId]/route";
import { PATCH as selectScenario } from "./[itemId]/selected-scenario/route";
import { GET as getDirectory } from "./route";

const apiGet = vi.hoisted(() => vi.fn());
const apiPatch = vi.hoisted(() => vi.fn());
vi.mock("@clearpath/api-client", () => ({ createClearPathClient: () => ({ GET: apiGet, PATCH: apiPatch }) }));

function me() { return { id: 1, email: "owner@example.com", display_name: "Owner", household_name: "Owner Home", selected_plan: "basic", billing_status: "active", is_admin: false, session_subject: { id: 1, subject_type: "user", email: "owner@example.com", display_name: "Owner", first_name: "Owner", avatar_initial: "O", household_role: null }, primary_account_holder: true, plan_display_name: "Plus", feature_access: [{ feature: "mortgage_loan_planning", enabled: true, hidden: false, required_plan: "Plus" }] }; }
function list() { return { items: [{ fixed_expense_item_id: 9, name: "Home Loan", loan_kind: "mortgage", monthly_payment: 1800, selected_extra: 200, total_monthly: 2000, principal_balance: 250000, current_balance: 245000, collateral_value: 320000, selected_scenario: "extra_one" }], total_debt_monthly: 2000, total_debt_balance: 245000, debt_to_income_ratio: .4, loan_category_label_options: ["Mortgage/Rent", "Vehicle Payments"], today: "2026-07-18", recurring_frequency_options: { monthly: "Monthly", semimonthly: "Twice Per Month" }, weekday_options: { 0: "Monday" }, monthly_week_options: { 1: "First" } }; }
function resource() { return { fixed_expense: { id: 9, name: "Home Loan", amount: 1800, due_day: 1, start_date: "2026-07-01", frequency: "monthly", days_of_week: null, second_date: null, second_day_of_month: null, monthly_week_numbers: null, monthly_weekday: null, category_label: "Mortgage/Rent", is_loan: true, notes: null, monthly_amount: 1800 }, loan_kind: "mortgage", plan: { id: 5, fixed_expense_item_id: 9, loan_type: "mortgage", principal_balance: 250000, collateral_value: 320000, annual_interest_rate: 6.5, term_months: 360, term_unit_preference: "years", regular_payment: 1800, extra_payment_one: 200, extra_payment_two: 400, selected_scenario: "extra_one", notes: "Home", created_at: "2026-07-01T00:00:00", updated_at: "2026-07-18T00:00:00" }, scenarios: [{ key: "base", label: "Base", extra_payment: 0, months: 360, years: 30, interest_paid: 398000, payoff_possible: true }], selected_schedule: [{ month: 1, payment_date: "2026-07-01", beginning_balance: 250000, payment: 2000, principal: 645, interest: 1355, ending_balance: 249355 }], created_fixed_expense: false }; }
function ok(data: unknown) { return { data, error: undefined, response: new Response(null, { status: 200 }) }; }
const context = { params: Promise.resolve({ itemId: "9" }) };

describe("loan planning BFF routes", () => {
  beforeEach(() => { apiGet.mockReset(); apiPatch.mockReset(); });

  it("maps the typed directory and creation options", async () => {
    apiGet.mockImplementation((path: string) => Promise.resolve(ok(path === "/v1/loan-plans" ? list() : me())));
    const response = await getDirectory(new Request("http://localhost/api/loan-plans", { headers: { cookie: "clearpath_session=full" } }));
    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({ totalDebtMonthly: 2000, debtToIncomeRatio: .4, today: "2026-07-18", items: [{ fixedExpenseItemId: 9, selectedExtra: 200 }], recurringFrequencyOptions: { semimonthly: "Twice Per Month" } });
  });

  it("combines a loan resource with session access", async () => {
    apiGet.mockImplementation((path: string) => Promise.resolve(ok(path === "/v1/me" ? me() : resource())));
    const response = await getDetail(new Request("http://localhost/api/loan-plans/9"), context);
    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({ session: { primaryAccountHolder: true }, resource: { loanKind: "mortgage", plan: { termUnitPreference: "years" }, selectedSchedule: [{ endingBalance: 249355 }] } });
  });

  it("validates and forwards the complete loan assumptions", async () => {
    apiPatch.mockResolvedValue(ok(resource()));
    const body = { principalBalance: 250000, collateralValue: 320000, annualInterestRate: 6.5, termValue: 30, termUnit: "years", regularPayment: 1800, extraPaymentOne: 200, extraPaymentTwo: 400, selectedScenario: "extra_one", notes: "Home" };
    const response = await updateDetail(new Request("http://localhost/api/loan-plans/9", { method: "PATCH", headers: { "content-type": "application/json", cookie: "clearpath_session=full" }, body: JSON.stringify(body) }), context);
    expect(response.status).toBe(200);
    expect(apiPatch).toHaveBeenCalledWith("/v1/loan-plans/{fixed_expense_item_id}", { params: { path: { fixed_expense_item_id: 9 } }, body: { principal_balance: 250000, collateral_value: 320000, annual_interest_rate: 6.5, term_value: 30, term_unit: "years", regular_payment: 1800, extra_payment_one: 200, extra_payment_two: 400, selected_scenario: "extra_one", notes: "Home" }, headers: { cookie: "clearpath_session=full" } });
  });

  it("keeps scenario selection as its own side-effecting mutation", async () => {
    apiPatch.mockResolvedValue(ok(resource()));
    const response = await selectScenario(new Request("http://localhost/api/loan-plans/9/selected-scenario", { method: "PATCH", headers: { "content-type": "application/json" }, body: JSON.stringify({ selectedScenario: "extra_two" }) }), context);
    expect(response.status).toBe(200);
    expect(apiPatch).toHaveBeenCalledWith("/v1/loan-plans/{fixed_expense_item_id}/selected-scenario", { params: { path: { fixed_expense_item_id: 9 } }, body: { selected_scenario: "extra_two" }, headers: {} });
  });
});
