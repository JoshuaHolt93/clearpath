import type { LoanPlanDirectory } from "@clearpath/validation";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { LoanDirectoryWorkspace } from "./loan-directory-workspace";

const navigation = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => navigation, usePathname: () => "/loan-plans" }));

function view(overrides: Partial<LoanPlanDirectory> = {}): LoanPlanDirectory { return { session: { ownerUserId: 1, householdName: "Owner Home", selectedPlan: "basic", billingStatus: "active", planDisplayName: "Plus", primaryAccountHolder: true, subject: { id: 1, subjectType: "user", email: "owner@example.com", displayName: "Owner", firstName: "Owner", avatarInitial: "O", householdRole: null }, featureAccess: [{ feature: "mortgage_loan_planning", enabled: true, hidden: false, requiredPlan: "Plus" }] }, items: [{ fixedExpenseItemId: 9, name: "Home Loan", loanKind: "mortgage", monthlyPayment: 1800, selectedExtra: 200, totalMonthly: 2000, principalBalance: 250000, currentBalance: 245000, collateralValue: 320000, selectedScenario: "extra_one" }], totalDebtMonthly: 2000, totalDebtBalance: 245000, debtToIncomeRatio: .4, loanCategoryLabelOptions: ["Mortgage/Rent", "Vehicle Payments"], today: "2026-07-18", recurringFrequencyOptions: { monthly: "Monthly", biweekly: "Every Two Weeks", semimonthly: "Twice Per Month" }, weekdayOptions: { 0: "Monday", 1: "Tuesday" }, monthlyWeekOptions: { 1: "First", 2: "Second" }, ...overrides }; }
function json(payload: unknown, status = 200) { return new Response(JSON.stringify(payload), { status, headers: { "content-type": "application/json" } }); }

describe("LoanDirectoryWorkspace", () => {
  beforeEach(() => { navigation.push.mockReset(); navigation.replace.mockReset(); navigation.refresh.mockReset(); vi.restoreAllMocks(); });

  it("renders Flask directory totals and tracked-loan details", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(json(view()));
    render(<LoanDirectoryWorkspace />);
    expect(await screen.findByText("$2,000")).toBeDefined();
    expect(screen.getByText("$245,000")).toBeDefined();
    expect(screen.getByText("40%")).toBeDefined();
    expect(screen.getByRole("heading", { name: "Home Loan" })).toBeDefined();
    expect(screen.getByRole("link", { name: "Open Full Schedule" }).getAttribute("href")).toBe("/loan-plans/9");
  });

  it("creates a fixed-expense-backed loan and opens its schedule", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(json(view())).mockResolvedValueOnce(json({ itemId: 22, name: "Auto Loan", monthlyAmount: 450 }, 201));
    render(<LoanDirectoryWorkspace />);
    fireEvent.change(await screen.findByLabelText("Loan Name"), { target: { value: "Auto Loan" } });
    fireEvent.change(screen.getByLabelText("Payment Amount"), { target: { value: "450" } });
    fireEvent.submit(screen.getByRole("button", { name: "Add Loan" }).closest("form")!);
    await waitFor(() => expect(navigation.push).toHaveBeenCalledWith("/loan-plans/22"));
    expect(JSON.parse(String((fetchMock.mock.calls[1]?.[1] as RequestInit).body))).toMatchObject({ name: "Auto Loan", amount: 450, frequency: "monthly", categoryLabel: "Mortgage/Rent", entryContext: "loan" });
  });

  it("renders cadence-specific and custom-category controls", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(json(view()));
    render(<LoanDirectoryWorkspace />);
    fireEvent.change(await screen.findByLabelText("Cadence"), { target: { value: "semimonthly" } });
    expect(screen.getByLabelText("Second Payment Date")).toBeDefined();
    fireEvent.change(screen.getByLabelText("Weekday Pattern"), { target: { value: "1" } });
    expect(screen.getByText("Weeks In Month")).toBeDefined();
    fireEvent.change(screen.getByLabelText("Loan Category"), { target: { value: "Other" } });
    expect(screen.getByLabelText("Custom Loan Category")).toBeDefined();
  });

  it("disables creation for shared viewers and redirects feature locks", async () => {
    const viewer = view({ session: { ...view().session, primaryAccountHolder: false, subject: { ...view().session.subject, subjectType: "household_member", householdRole: "viewer" } } });
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(json(viewer));
    const first = render(<LoanDirectoryWorkspace />);
    expect((await screen.findByRole("button", { name: "Add Loan" }) as HTMLButtonElement).disabled).toBe(true);
    first.unmount();
    vi.restoreAllMocks();
    vi.spyOn(globalThis, "fetch").mockResolvedValue(json({ message: "Upgrade" }, 403));
    render(<LoanDirectoryWorkspace />);
    await waitFor(() => expect(navigation.replace).toHaveBeenCalledWith("/select-plan"));
  });
});
