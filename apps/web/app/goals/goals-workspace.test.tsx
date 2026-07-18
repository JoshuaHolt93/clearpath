import type { GoalsView } from "@clearpath/validation";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { GoalsWorkspace } from "./goals-workspace";

vi.mock("next/navigation", () => ({ usePathname: () => "/goals", useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }) }));

function view(overrides: Partial<GoalsView> = {}): GoalsView {
  return { session: { ownerUserId: 1, householdName: "Owner Home", selectedPlan: "premium", billingStatus: "active", planDisplayName: "Premier", primaryAccountHolder: true, subject: { id: 1, subjectType: "user", email: "owner@example.com", displayName: "Owner", firstName: "Owner", avatarInitial: "O", householdRole: null }, featureAccess: [{ feature: "mortgage_loan_planning", enabled: true, hidden: false, requiredPlan: "Plus" }, { feature: "retirement_planning", enabled: true, hidden: false, requiredPlan: "Premier" }] }, goals: [{ id: 4, name: "Emergency Fund", goalType: "savings", targetAmount: 12000, currentAmount: 3000, monthlyContribution: 500, targetDate: "2027-01-31", fixedExpenseItemId: null, progress: 25, timeline: "18 months", remaining: 9000, requiredMonthly: 1500, requiredExtra: 0, linkedItem: null }, { id: 5, name: "Home Payoff", goalType: "debt", targetAmount: 245000, currentAmount: 5000, monthlyContribution: 200, targetDate: "2032-01-01", fixedExpenseItemId: 9, progress: 2, timeline: "27 years", remaining: 240000, requiredMonthly: 0, requiredExtra: 350, linkedItem: { id: 9, name: "Home Loan" } }], loanOptions: [{ fixedExpenseItemId: 9, name: "Home Loan", loanKind: "mortgage", monthlyPayment: 1800, selectedExtra: 200, totalMonthly: 2000, principalBalance: 250000, currentBalance: 245000, collateralValue: 320000, selectedScenario: "extra" }], ...overrides };
}
function json(payload: unknown, status = 200) { return new Response(JSON.stringify(payload), { status, headers: { "content-type": "application/json" } }); }

describe("GoalsWorkspace", () => {
  beforeEach(() => { vi.restoreAllMocks(); vi.spyOn(window, "confirm").mockReturnValue(true); });

  it("renders savings and linked-debt calculations from the API", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(json(view()));
    render(<GoalsWorkspace />);
    expect(await screen.findByText("Emergency Fund")).toBeDefined();
    expect(screen.getByText("Needed: $1,500 / Month")).toBeDefined();
    expect(screen.getByText("Linked To Home Loan")).toBeDefined();
    expect(screen.getByText("Extra Needed: $350 / Month")).toBeDefined();
  });

  it("creates a linked debt goal and reloads canonical rows", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (_input, init) => init?.method === "POST" ? json({ id: 6 }, 201) : json(view()));
    render(<GoalsWorkspace />);
    await screen.findByText("Emergency Fund");
    const form = screen.getByRole("button", { name: "Add Goal" }).closest("form")!;
    fireEvent.change(within(form).getByLabelText("Goal Name"), { target: { value: "Mortgage Sprint" } });
    fireEvent.change(within(form).getByLabelText("Goal Type"), { target: { value: "debt" } });
    fireEvent.change(within(form).getByLabelText("Debt This Goal Applies To"), { target: { value: "9" } });
    fireEvent.click(within(form).getByRole("button", { name: "Add Goal" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    expect(JSON.parse(String(fetchMock.mock.calls[1]?.[1]?.body))).toMatchObject({ name: "Mortgage Sprint", goalType: "debt", fixedExpenseItemId: 9 });
    expect(await screen.findByText("Goal created.")).toBeDefined();
  });

  it("edits all goal fields in the modal and restores body scrolling", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (_input, init) => init?.method === "PATCH" ? json({ id: 4 }) : json(view()));
    render(<GoalsWorkspace />);
    await screen.findByText("Emergency Fund");
    fireEvent.click(screen.getByRole("button", { name: "Edit Emergency Fund" }));
    expect(document.body.style.overflow).toBe("hidden");
    const dialog = screen.getByRole("dialog", { name: "Edit Goal" });
    fireEvent.change(within(dialog).getByLabelText("Monthly Contribution"), { target: { value: "650" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save Goal" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    expect(JSON.parse(String(fetchMock.mock.calls[1]?.[1]?.body))).toMatchObject({ name: "Emergency Fund", monthlyContribution: 650 });
    await waitFor(() => expect(document.body.style.overflow).toBe(""));
  });

  it("deletes only after confirmation", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (_input, init) => init?.method === "DELETE" ? json({ deletedGoalId: 4 }) : json(view()));
    render(<GoalsWorkspace />);
    await screen.findByText("Emergency Fund");
    fireEvent.click(screen.getByRole("button", { name: "Delete Emergency Fund" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    expect(window.confirm).toHaveBeenCalledWith("Delete Emergency Fund?");
  });

  it("keeps shared viewers read-only and shows plan guidance", async () => {
    const base = view();
    vi.spyOn(globalThis, "fetch").mockResolvedValue(json(view({ session: { ...base.session, primaryAccountHolder: false, subject: { ...base.session.subject, subjectType: "household_member", householdRole: "viewer" }, featureAccess: [{ feature: "mortgage_loan_planning", enabled: false, hidden: false, requiredPlan: "Plus" }] } })));
    render(<GoalsWorkspace />);
    expect(await screen.findByText("Shared viewer access is read-only.")).toBeDefined();
    expect(screen.getByRole("button", { name: "Add Goal" }).hasAttribute("disabled")).toBe(true);
    expect(screen.getByRole("button", { name: "Edit Emergency Fund" }).hasAttribute("disabled")).toBe(true);
    expect(screen.getByRole("link", { name: "Upgrade To Plus" }).getAttribute("href")).toBe("/select-plan");
  });
});
