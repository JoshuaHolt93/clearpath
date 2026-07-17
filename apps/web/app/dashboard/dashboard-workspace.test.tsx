import type { DashboardView } from "@clearpath/validation";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DashboardWorkspace } from "./dashboard-workspace";

const navigation = vi.hoisted(() => ({ replace: vi.fn(), refresh: vi.fn() }));

vi.mock("next/navigation", () => ({
  usePathname: () => "/dashboard",
  useRouter: () => navigation,
}));

function dashboard(overrides: Partial<DashboardView> = {}): DashboardView {
  return {
    session: {
      ownerUserId: 1,
      householdName: "Parker Household",
      selectedPlan: "premium",
      billingStatus: "active",
      planDisplayName: "Premier",
      primaryAccountHolder: true,
      subject: { id: 1, subjectType: "user", email: "parker@example.com", displayName: "Parker User", firstName: "Parker", avatarInitial: "P", householdRole: null },
      featureAccess: [
        { feature: "income_planning", enabled: true, hidden: false, requiredPlan: "Plus" },
        { feature: "cash_projection", enabled: true, hidden: false, requiredPlan: "Plus" },
        { feature: "subscriptions", enabled: true, hidden: false, requiredPlan: "Plus" },
        { feature: "ai_planner", enabled: true, hidden: false, requiredPlan: "Premier" },
        { feature: "ai_coach", enabled: true, hidden: false, requiredPlan: "Premier" },
        { feature: "mortgage_loan_planning", enabled: true, hidden: false, requiredPlan: "Plus" },
        { feature: "retirement_planning", enabled: true, hidden: false, requiredPlan: "Premier" },
      ],
    },
    monthName: "July 2026",
    today: "2026-07-16",
    elapsedDays: 16,
    totalDays: 31,
    daysLeft: 15,
    pacePercent: 51.6,
    spendPercent: 6.3,
    showTutorial: true,
    metrics: { monthIncome: 5000, fixedExpenses: 1800, variableSpend: 200, safeToSpend: 3000, safeToSpendTarget: 3200, netCashFlow: 3000, onTrackStatus: "green", expectedVariableSpend: 1600 },
    netWorth: { assets: 60000, liabilities: 105000, netWorth: -45000 },
    categoryTotals: [{ category: "Groceries", categoryId: 3, amount: 200 }],
    goals: [{ id: 4, name: "Family Loan", goalType: "debt", progress: 40, timeline: "30 months", currentAmount: 2000, targetAmount: 5000, requiredMonthly: 0, requiredExtra: 0, targetDate: "2027-01-31" }],
    recentTransactions: [{ id: 7, postedDate: "2026-07-16", description: "Grocery Run", amount: -200, transactionType: "expense", categoryName: "Groceries" }],
    planRows: [{ label: "Expenses", planned: 2400, actual: 2000, type: "expense", details: [{ label: "Groceries", planned: 600, actual: 200, source: "transactions" }] }],
    budgetRemaining: 400,
    expectedCashFlow: 2600,
    insights: [{ title: "Room to build savings", body: "Your plan has a surplus.", level: "good", type: "surplus_opportunity", disclaimer: "Educational guidance only." }],
    dashboardFocus: { items: [], generatedAt: null, message: "Generate guidance to add a dashboard focus." },
    ...overrides,
  };
}

describe("DashboardWorkspace", () => {
  beforeEach(() => {
    navigation.replace.mockReset();
    navigation.refresh.mockReset();
    vi.restoreAllMocks();
  });

  it("refreshes through the explicit mutation, then renders canonical dashboard sections", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify({ synced: 1, errors: [] }), { status: 200, headers: { "content-type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify(dashboard()), { status: 200, headers: { "content-type": "application/json" } }));
    render(<DashboardWorkspace initialWelcome />);

    expect(await screen.findByRole("heading", { name: /Good .* Parker/ })).toBeDefined();
    expect(screen.getByText("On Track")).toBeDefined();
    expect(screen.getByRole("heading", { name: "Welcome To Today" })).toBeDefined();
    expect(screen.getByRole("heading", { name: "Current Month Plan vs Actual" })).toBeDefined();
    expect(screen.getByRole("heading", { name: "Where The Money Went" })).toBeDefined();
    expect(screen.getByText("Grocery Run")).toBeDefined();
    expect(screen.getByRole("link", { name: "AI Planner" })).toBeDefined();
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/plaid-items/refresh-stale");
    expect(fetchMock.mock.calls[1]?.[0]).toBe("/api/dashboard?welcome=1");
  });

  it("allows an editor principal to delete the inline goal", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify({ synced: 0, errors: [] }), { status: 200, headers: { "content-type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify(dashboard()), { status: 200, headers: { "content-type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ deletedGoalId: 4 }), { status: 200, headers: { "content-type": "application/json" } }));
    render(<DashboardWorkspace initialWelcome={false} />);

    const deleteButton = await screen.findByRole("button", { name: "Delete Family Loan" });
    fireEvent.click(deleteButton);
    await waitFor(() => expect(screen.queryByText("Family Loan")).toBeNull());
    expect(fetchMock.mock.calls[2]?.[0]).toBe("/api/goals/4");
    expect(fetchMock.mock.calls[2]?.[1]).toMatchObject({ method: "DELETE" });
  });

  it("keeps shared viewers read-only in the dashboard shell", async () => {
    const viewer = dashboard({
      session: {
        ...dashboard().session,
        primaryAccountHolder: false,
        subject: { id: 8, subjectType: "household_member", email: "viewer@example.com", displayName: "Taylor Viewer", firstName: "Taylor", avatarInitial: "T", householdRole: "viewer" },
      },
    });
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify({ message: "Shared household access is view-only." }), { status: 403, headers: { "content-type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify(viewer), { status: 200, headers: { "content-type": "application/json" } }));
    render(<DashboardWorkspace initialWelcome={false} />);

    expect(await screen.findByRole("heading", { name: /Good .* Taylor/ })).toBeDefined();
    expect(screen.queryByRole("button", { name: "Delete Family Loan" })).toBeNull();
    expect(screen.queryByRole("link", { name: "Upgrade Account" })).toBeNull();
  });
});
