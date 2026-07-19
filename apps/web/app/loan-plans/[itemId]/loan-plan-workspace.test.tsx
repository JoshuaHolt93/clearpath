import type { LoanPlanDetail, LoanPlanResource } from "@clearpath/validation";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { LoanPlanWorkspace } from "./loan-plan-workspace";

const navigation = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => navigation, usePathname: () => "/loan-plans/9" }));

function resource(overrides: Partial<LoanPlanResource> = {}): LoanPlanResource { return { fixedExpense: { id: 9, name: "Home Loan", amount: 1800, frequency: "monthly", startDate: "2026-07-01", categoryLabel: "Mortgage/Rent", isLoan: true, monthlyAmount: 1800 }, loanKind: "mortgage", plan: { id: 5, fixedExpenseItemId: 9, loanType: "mortgage", principalBalance: 250000, collateralValue: 320000, annualInterestRate: 6.5, termMonths: 360, termUnitPreference: "years", regularPayment: 1800, extraPaymentOne: 200, extraPaymentTwo: 400, selectedScenario: "extra_one", notes: "Home" }, scenarios: [{ key: "base", label: "Base", extraPayment: 0, months: 360, years: 30, interestPaid: 398000, payoffPossible: true }, { key: "extra_one", label: "Extra 1", extraPayment: 200, months: 290, years: 24.2, interestPaid: 300000, payoffPossible: true }], selectedSchedule: [{ month: 1, paymentDate: "2026-07-01", beginningBalance: 250000, payment: 2000, principal: 645, interest: 1355, endingBalance: 249355 }], createdFixedExpense: false, ...overrides }; }
function detail(overrides: Partial<LoanPlanDetail> = {}): LoanPlanDetail { return { session: { ownerUserId: 1, householdName: "Owner Home", selectedPlan: "basic", billingStatus: "active", planDisplayName: "Plus", primaryAccountHolder: true, subject: { id: 1, subjectType: "user", email: "owner@example.com", displayName: "Owner", firstName: "Owner", avatarInitial: "O", householdRole: null }, featureAccess: [{ feature: "mortgage_loan_planning", enabled: true, hidden: false, requiredPlan: "Plus" }] }, resource: resource(), ...overrides }; }
function json(payload: unknown, status = 200) { return new Response(JSON.stringify(payload), { status, headers: { "content-type": "application/json" } }); }

describe("LoanPlanWorkspace", () => {
  beforeEach(() => { navigation.push.mockReset(); navigation.replace.mockReset(); navigation.refresh.mockReset(); vi.restoreAllMocks(); });

  it("renders assumptions, scenario comparison, and the server schedule", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(json(detail()));
    render(<LoanPlanWorkspace itemId="9" />);
    expect(await screen.findByRole("heading", { name: "Mortgage Details" })).toBeDefined();
    expect(screen.getByRole("heading", { name: "Scenario Comparison" })).toBeDefined();
    expect(screen.getByRole("heading", { name: "Full Amortization Schedule" })).toBeDefined();
    expect(screen.getByText("$249,355.00")).toBeDefined();
  });

  it("saves complete assumptions without client amortization math", async () => {
    const updated = resource({ plan: { ...resource().plan!, principalBalance: 240000 } });
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(json(detail())).mockResolvedValueOnce(json(updated));
    render(<LoanPlanWorkspace itemId="9" />);
    fireEvent.change(await screen.findByLabelText("Principal Balance"), { target: { value: "240000" } });
    fireEvent.submit(screen.getByRole("button", { name: "Save Loan Details" }).closest("form")!);
    expect(await screen.findByText("Amortization schedule updated.")).toBeDefined();
    expect(JSON.parse(String((fetchMock.mock.calls[1]?.[1] as RequestInit).body))).toMatchObject({ principalBalance: 240000, termValue: 30, termUnit: "years", selectedScenario: "extra_one" });
  });

  it("selects a server scenario and applies the returned schedule", async () => {
    const selected = resource({ plan: { ...resource().plan!, selectedScenario: "base" } });
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(json(detail())).mockResolvedValueOnce(json(selected));
    render(<LoanPlanWorkspace itemId="9" />);
    fireEvent.click(await screen.findByRole("button", { name: "Select" }));
    expect(await screen.findByText("Selected payoff plan updated.")).toBeDefined();
    expect(fetchMock.mock.calls[1]?.[0]).toBe("/api/loan-plans/9/selected-scenario");
  });

  it("keeps the detail read-only for shared viewers", async () => {
    const viewer = detail({ session: { ...detail().session, primaryAccountHolder: false, subject: { ...detail().session.subject, subjectType: "household_member", householdRole: "viewer" } } });
    vi.spyOn(globalThis, "fetch").mockResolvedValue(json(viewer));
    render(<LoanPlanWorkspace itemId="9" />);
    expect((await screen.findByRole("button", { name: "Save Loan Details" }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole("button", { name: "Select" }) as HTMLButtonElement).disabled).toBe(true);
  });
});
