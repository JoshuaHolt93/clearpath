import { beforeEach, describe, expect, it, vi } from "vitest";

import { PATCH } from "./[goalId]/route";
import { GET, POST } from "./route";

const apiGet = vi.hoisted(() => vi.fn());
const apiPost = vi.hoisted(() => vi.fn());
const apiPatch = vi.hoisted(() => vi.fn());
vi.mock("@clearpath/api-client", () => ({ createClearPathClient: () => ({ GET: apiGet, POST: apiPost, PATCH: apiPatch }) }));

function goalResponse() {
  return { goal: { id: 4, name: "Emergency Fund", goal_type: "savings", target_amount: 12000, current_amount: 3000, monthly_contribution: 500, target_date: "2027-01-31", fixed_expense_item_id: null }, progress: 25, timeline: "18 months", remaining: 9000, current_amount: 3000, target_amount: 12000, required_monthly: 1500, required_extra: 0, linked_item: null };
}

function listResponse() {
  return { goals: [goalResponse()], loan_options: [{ fixed_expense_item_id: 9, name: "Home Loan", loan_kind: "mortgage", monthly_payment: 1800, selected_extra: 200, total_monthly: 2000, principal_balance: 250000, current_balance: 245000, collateral_value: 320000, selected_scenario: "extra" }] };
}

function meResponse() {
  return { id: 1, email: "owner@example.com", display_name: "Owner", household_name: "Owner Home", selected_plan: "premium", billing_status: "active", is_admin: false, session_subject: { id: 1, subject_type: "user", email: "owner@example.com", display_name: "Owner", first_name: "Owner", avatar_initial: "O", household_role: null }, primary_account_holder: true, plan_display_name: "Premier", feature_access: [{ feature: "mortgage_loan_planning", enabled: true, hidden: false, required_plan: "Plus" }] };
}

const mutation = { name: "Home Payoff", goalType: "debt", targetAmount: 245000, currentAmount: 5000, monthlyContribution: 200, targetDate: "2032-01-01", fixedExpenseItemId: 9 };

describe("goal BFF routes", () => {
  beforeEach(() => { apiGet.mockReset(); apiPost.mockReset(); apiPatch.mockReset(); });

  it("combines goal rows, loan options, and session access", async () => {
    apiGet.mockImplementation((path: string) => Promise.resolve({ data: path === "/v1/goals" ? listResponse() : meResponse(), error: undefined, response: new Response(null, { status: 200 }) }));
    const response = await GET(new Request("http://localhost/api/goals", { headers: { cookie: "clearpath_session=full" } }));
    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({ session: { primaryAccountHolder: true }, goals: [{ name: "Emergency Fund", requiredMonthly: 1500 }], loanOptions: [{ name: "Home Loan", currentBalance: 245000 }] });
    expect(apiGet).toHaveBeenCalledWith("/v1/goals", { headers: { cookie: "clearpath_session=full" } });
    expect(response.headers.get("cache-control")).toBe("no-store");
  });

  it("creates a linked debt goal with the exact typed payload", async () => {
    apiPost.mockResolvedValue({ data: goalResponse(), error: undefined, response: new Response(null, { status: 201 }) });
    const response = await POST(new Request("http://localhost/api/goals", { method: "POST", headers: { "content-type": "application/json", cookie: "clearpath_session=full" }, body: JSON.stringify(mutation) }));
    expect(response.status).toBe(201);
    expect(apiPost).toHaveBeenCalledWith("/v1/goals", { body: { name: "Home Payoff", goal_type: "debt", target_amount: 245000, current_amount: 5000, monthly_contribution: 200, target_date: "2032-01-01", fixed_expense_item_id: 9 }, headers: { cookie: "clearpath_session=full" } });
  });

  it("updates the complete Goal edit form through PATCH", async () => {
    apiPatch.mockResolvedValue({ data: goalResponse(), error: undefined, response: new Response(null, { status: 200 }) });
    const response = await PATCH(new Request("http://localhost/api/goals/4", { method: "PATCH", headers: { "content-type": "application/json", cookie: "clearpath_session=full" }, body: JSON.stringify(mutation) }), { params: Promise.resolve({ goalId: "4" }) });
    expect(response.status).toBe(200);
    expect(apiPatch).toHaveBeenCalledWith("/v1/goals/{goal_id}", expect.objectContaining({ params: { path: { goal_id: 4 } }, body: expect.objectContaining({ fixed_expense_item_id: 9, monthly_contribution: 200 }) }));
  });
});
