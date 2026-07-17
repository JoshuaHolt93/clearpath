import type { MonthlyBudgetsView } from "@clearpath/validation";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { MonthlyBudgetsWorkspace, type MonthlyBudgetQuery } from "./monthly-budgets-workspace";

const navigation = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }));

vi.mock("next/navigation", () => ({ usePathname: () => "/monthly-plan", useRouter: () => navigation }));

const query: MonthlyBudgetQuery = { budgetView: "list", budgetSort: "custom", budgetMonth: "", onboardingComplete: true };

function row(overrides: Partial<MonthlyBudgetsView["budgetSections"][number]["rows"][number]> = {}) {
  return {
    kind: "category",
    categoryKind: "expense",
    categoryId: 3,
    label: "Groceries",
    category: "Groceries",
    groupKey: "daily_living",
    planned: 600,
    actual: 250,
    remaining: 350,
    progressPercent: 41.6667,
    progressStatus: "ok",
    anchorId: "budget-groceries",
    transactionIds: [8],
    transactionCount: 1,
    suggestionMatchCount: 0,
    sortOrder: 1,
    canRemoveBudget: true,
    actualLabel: "spent",
    plannedLabel: "planned",
    adjustLabel: "",
    amortizationAction: null,
    ...overrides,
  };
}

function view(overrides: Partial<MonthlyBudgetsView> = {}): MonthlyBudgetsView {
  return {
    session: {
      ownerUserId: 1,
      householdName: "Parker Household",
      selectedPlan: "premium",
      billingStatus: "active",
      planDisplayName: "Premier",
      primaryAccountHolder: true,
      subject: { id: 1, subjectType: "user", email: "parker@example.com", displayName: "Parker User", firstName: "Parker", avatarInitial: "P", householdRole: null },
      featureAccess: [{ feature: "subscriptions", enabled: true, hidden: false, requiredPlan: "Plus" }],
    },
    monthName: "July 2026",
    today: "2026-07-17",
    onboardingComplete: true,
    budgetView: "list",
    budgetGrouped: false,
    budgetSort: "custom",
    budgetDragEnabled: true,
    budgetSelectedMonth: "2026-07-01",
    budgetCurrentMonth: "2026-07-01",
    budgetMonthValue: "2026-07",
    budgetMonthLabel: "July 2026",
    budgetIsCurrentMonth: true,
    budgetHistoryMode: false,
    totalBudgetPlanned: 600,
    totalBudgetActual: 290,
    totalBudgetRemaining: 310,
    expectedCashFlow: 4600,
    budgetSections: [{ label: "Expense Budgets", kind: "list", description: "Review each expense budget.", empty: "No category budgets.", rows: [row()], planned: 600, actual: 250, transactionIds: [8], transactionCount: 1 }],
    suggestedBudgetSections: [{ label: "Suggestions", kind: "list", rows: [row({ categoryId: 4, category: "Fuel/Gasoline", label: "Fuel/Gasoline", planned: 75, actual: 0, remaining: 75, suggestionMatchCount: 2, transactionIds: [9, 10], transactionCount: 2 })] }],
    unassignedBudgetRows: [row({ kind: "cleanup", categoryKind: "cleanup", categoryId: null, category: "Other Spending To Categorize", label: "Other Spending To Categorize", planned: 0, actual: 40, remaining: -40, progressPercent: 100, progressStatus: "over", anchorId: "budget-cleanup", transactionIds: [11], canRemoveBudget: false, actualLabel: "needs review", plannedLabel: "not budgeted" })],
    categoryLabelOptions: ["Groceries", "Fuel/Gasoline"],
    budgetGroupOptions: [{ key: "daily_living", label: "Daily Living", description: "Everyday household costs." }],
    budgetSortOptions: { custom: "Custom Order", amount_desc: "Highest Budget First", amount_asc: "Lowest Budget First", category_az: "Category A-Z", category_za: "Category Z-A" },
    ...overrides,
  };
}

describe("MonthlyBudgetsWorkspace", () => {
  beforeEach(() => {
    navigation.push.mockReset();
    navigation.replace.mockReset();
    navigation.refresh.mockReset();
    vi.restoreAllMocks();
  });

  it("refreshes explicitly and renders current budgets, cleanup, suggestions, and onboarding state", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify({ synced: 0, errors: [] }), { status: 200, headers: { "content-type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify(view()), { status: 200, headers: { "content-type": "application/json" } }));
    render(<MonthlyBudgetsWorkspace query={query} />);

    expect(await screen.findByRole("heading", { name: "Budgets", level: 1 })).toBeDefined();
    expect(screen.getByText("Your first budgets are started.")).toBeDefined();
    expect(screen.getByText("Groceries")).toBeDefined();
    expect(screen.getByRole("heading", { name: "Other Spending To Categorize" })).toBeDefined();
    expect(screen.getByText("Suggested Categories")).toBeDefined();
    expect(screen.getByRole("link", { name: "Budgets" }).getAttribute("class")).toContain("active");
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/plaid-items/refresh-stale");
    expect(String(fetchMock.mock.calls[1]?.[0])).toContain("/api/monthly-plan?section=budgets");
  });

  it("saves an inline amount then reloads the canonical budget resource", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify({ synced: 0, errors: [] }), { status: 200, headers: { "content-type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify(view()), { status: 200, headers: { "content-type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ categoryId: 3, monthlyTarget: 650 }), { status: 200, headers: { "content-type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ synced: 0, errors: [] }), { status: 200, headers: { "content-type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify(view({ totalBudgetPlanned: 650, budgetSections: [{ ...view().budgetSections[0], planned: 650, rows: [row({ planned: 650, remaining: 400 })] }] })), { status: 200, headers: { "content-type": "application/json" } }));
    render(<MonthlyBudgetsWorkspace query={{ ...query, onboardingComplete: false }} />);

    const amount = await screen.findByRole("spinbutton", { name: "Budget amount for Groceries" });
    fireEvent.change(amount, { target: { value: "650" } });
    fireEvent.click(screen.getByRole("button", { name: "Save Groceries budget" }));
    await waitFor(() => expect(screen.getByText("Groceries updated.")).toBeDefined());
    expect(fetchMock.mock.calls[2]?.[0]).toBe("/api/budgets/3");
    expect(fetchMock.mock.calls[2]?.[1]).toMatchObject({ method: "PATCH" });
    expect(JSON.parse(String(fetchMock.mock.calls[2]?.[1]?.body))).toEqual({ monthlyTarget: 650, budgetMonth: "2026-07" });
  });

  it("resets the captured form after creating a budget", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify({ synced: 0, errors: [] }), { status: 200, headers: { "content-type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify(view()), { status: 200, headers: { "content-type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ categoryId: 4, category: "Books", monthlyTarget: 50 }), { status: 201, headers: { "content-type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ synced: 0, errors: [] }), { status: 200, headers: { "content-type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify(view()), { status: 200, headers: { "content-type": "application/json" } }));
    render(<MonthlyBudgetsWorkspace query={{ ...query, onboardingComplete: false }} />);

    const category = await screen.findByRole("combobox", { name: "Category" }) as HTMLInputElement;
    const amount = screen.getByRole("spinbutton", { name: "Monthly Budget" }) as HTMLInputElement;
    fireEvent.change(category, { target: { value: "Books" } });
    fireEvent.change(amount, { target: { value: "50" } });
    fireEvent.click(screen.getByRole("button", { name: "Add Budget" }));

    await waitFor(() => expect(screen.getByText("Books added.")).toBeDefined());
    expect(category.value).toBe("");
    expect(amount.value).toBe("");
    expect(fetchMock.mock.calls[2]?.[0]).toBe("/api/budgets");
  });

  it("keeps a shared viewer and historical month read-only", async () => {
    const history = view({
      onboardingComplete: false,
      budgetHistoryMode: true,
      budgetIsCurrentMonth: false,
      budgetMonthValue: "2026-06",
      budgetMonthLabel: "June 2026",
      budgetDragEnabled: false,
      session: { ...view().session, primaryAccountHolder: false, subject: { ...view().session.subject, subjectType: "household_member", householdRole: "viewer", displayName: "Taylor Viewer", email: "viewer@example.com" } },
    });
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify({ message: "View only" }), { status: 403, headers: { "content-type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify(history), { status: 200, headers: { "content-type": "application/json" } }));
    render(<MonthlyBudgetsWorkspace query={{ ...query, budgetMonth: "2026-06", onboardingComplete: false }} />);

    expect(await screen.findByText("This is a read-only historical budget. Current category changes do not rewrite June 2026.")).toBeDefined();
    expect(screen.queryByRole("spinbutton", { name: "Budget amount for Groceries" })).toBeNull();
    expect(screen.queryByText("Add Budget")).toBeNull();
    expect(screen.queryByRole("button", { name: "Remove Groceries" })).toBeNull();
  });
});
