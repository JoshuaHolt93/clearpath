import type { AnalyticsView } from "@clearpath/validation";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AnalyticsWorkspace, type AnalyticsQuery } from "./analytics-workspace";

const navigation = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => navigation, usePathname: () => "/analytics" }));

const query: AnalyticsQuery = { range: "month", endMonth: "2026-07", historyRange: "quarter", historyEndMonth: "2026-07" };

function view(overrides: Partial<AnalyticsView> = {}): AnalyticsView {
  const subscription = { id: 8, name: "Stream Box", serviceCategory: "Streaming", monthlyAmount: 20, annualAmount: 240, cycle: "Monthly", confidence: .9, status: "active", replaceable: true, nextChargeDate: "2026-07-28" };
  const snapshot = { month: "2026-07-01", plannedIncome: 5000, plannedFixedExpenses: 1800, plannedVariableExpenses: 800, plannedSavings: 400, plannedDebtPayment: 250, plannedTaxes: 700, plannedRetirement: 300, plannedSafeToSpend: 800, expectedCashFlow: 1700, budgetRemaining: 500, actualIncome: 4900, actualFixedExpenses: 1750, actualVariableExpenses: 725, actualTotalExpenses: 2475, netCashFlow: 2425 };
  const summary = { rangeKey: "month", rangeLabel: "Month", months: ["2026-07-01"], snapshots: [snapshot], startDate: "2026-07-01", endDate: "2026-07-31", totalIncome: 4900, totalSpending: 2475, totalExpectedCashFlow: 1700, totalNetCashFlow: 2425, averageIncome: 4900, averageSpending: 2475, averageNetCashFlow: 2425, maxIncome: 5000, maxSpending: 3300, maxCashFlow: 2425, categoryRows: [{ category: "Groceries", categoryId: 3, amount: 425 }], subscriptions: { subscriptions: [subscription], activeCount: 1, reviewCount: 0, actionCount: 1, manageLinkCount: 0, monthlyTotal: 20, annualTotal: 240, potentialSavings: 20, spendingShare: 1, categoryBreakdown: [{ category: "Streaming", amount: 20, percent: 100 }], opportunities: [{ subscription, reason: "Replaceable service" }], upcoming: [subscription] } };
  return { session: { ownerUserId: 1, householdName: "Owner Home", selectedPlan: "premium", billingStatus: "active", planDisplayName: "Premier", primaryAccountHolder: true, subject: { id: 1, subjectType: "user", email: "owner@example.com", displayName: "Owner", firstName: "Owner", avatarInitial: "O", householdRole: null }, featureAccess: [] }, summary, budgetHistorySummary: { ...summary, rangeKey: "quarter", rangeLabel: "Quarter" }, debtToIncomeRatio: .32, rangeOptions: { month: "Month", quarter: "Quarter", six_months: "6 Months", year: "1 Year" }, selectedRange: "month", endMonth: "2026-07-01", selectedHistoryRange: "quarter", historyEndMonth: "2026-07-01", subscriptionAnalyticsEnabled: true, subscriptionAnalyticsPlanLabel: "Plus", aiCoachEnabled: true, aiCoachHidden: false, ...overrides };
}

function json(payload: unknown, status = 200) { return new Response(JSON.stringify(payload), { status, headers: { "content-type": "application/json" } }); }

describe("AnalyticsWorkspace", () => {
  beforeEach(() => { navigation.push.mockReset(); navigation.replace.mockReset(); navigation.refresh.mockReset(); vi.restoreAllMocks(); });

  it("renders all Flask analytics sections from one read-only request", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(json(view()));
    render(<AnalyticsWorkspace query={query} />);
    expect(await screen.findByRole("heading", { name: "Income History" })).toBeDefined();
    expect(screen.getByRole("heading", { name: "Spending History" })).toBeDefined();
    expect(screen.getByRole("heading", { name: "Cash Flow History" })).toBeDefined();
    expect(screen.getByRole("heading", { name: "Spending By Category" })).toBeDefined();
    expect(screen.getByRole("heading", { name: "Subscriptions Analytics" })).toBeDefined();
    expect(screen.getByRole("heading", { name: "Monthly Budget History" })).toBeDefined();
    expect(screen.getByText("32%")).toBeDefined();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("keeps the primary and history range filters independent", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(json(view()));
    render(<AnalyticsWorkspace query={query} />);
    await screen.findByText("Financial Trends");
    const primaryForm = screen.getByLabelText("Range").closest("form")!;
    fireEvent.change(within(primaryForm).getByLabelText("Range"), { target: { value: "year" } });
    fireEvent.change(within(primaryForm).getByLabelText("Ending Month"), { target: { value: "2026-06" } });
    fireEvent.submit(primaryForm);
    expect(navigation.push).toHaveBeenCalledWith("/analytics?range=year&history_range=quarter&end_month=2026-06&history_end_month=2026-07");
    const historyForm = screen.getByLabelText("Budget History Range").closest("form")!;
    fireEvent.change(within(historyForm).getByLabelText("Budget History Range"), { target: { value: "six_months" } });
    fireEvent.submit(historyForm);
    expect(navigation.push).toHaveBeenLastCalledWith("/analytics?range=month&history_range=six_months&end_month=2026-07&history_end_month=2026-07");
  });

  it("shows the subscription upgrade state without hiding core analytics", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(json(view({ subscriptionAnalyticsEnabled: false, aiCoachEnabled: false })));
    render(<AnalyticsWorkspace query={query} />);
    expect(await screen.findByRole("heading", { name: "See subscription impact after you upgrade." })).toBeDefined();
    expect(screen.getByRole("link", { name: "Upgrade To Plus" }).getAttribute("href")).toBe("/select-plan");
    expect(screen.getByRole("heading", { name: "Spending By Category" })).toBeDefined();
  });

  it("surfaces a load error and retries", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(json({ message: "Analytics unavailable" }, 503)).mockResolvedValueOnce(json(view()));
    render(<AnalyticsWorkspace query={query} />);
    expect((await screen.findByRole("alert")).textContent).toContain("Analytics unavailable");
    fireEvent.click(screen.getByRole("button", { name: "Try Again" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(await screen.findByRole("heading", { name: "Monthly Budget History" })).toBeDefined();
  });
});
