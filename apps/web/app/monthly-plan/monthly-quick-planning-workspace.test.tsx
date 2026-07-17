import type { MonthlyQuickPlanningView } from "@clearpath/validation";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { MonthlyQuickPlanningWorkspace, type MonthlyQuickPlanningQuery } from "./monthly-quick-planning-workspace";

const navigation = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }));
vi.mock("next/navigation", () => ({ usePathname: () => "/monthly-plan", useRouter: () => navigation }));

const query: MonthlyQuickPlanningQuery = { quickSort: "amount_desc" };

function view(overrides: Partial<MonthlyQuickPlanningView> = {}): MonthlyQuickPlanningView {
  return {
    session: {
      ownerUserId: 1, householdName: "Parker Household", selectedPlan: "premium", billingStatus: "active", planDisplayName: "Premier", primaryAccountHolder: true,
      subject: { id: 1, subjectType: "user", email: "parker@example.com", displayName: "Parker User", firstName: "Parker", avatarInitial: "P", householdRole: null },
      featureAccess: [{ feature: "cash_projection", enabled: true, hidden: false, requiredPlan: "Premier" }, { feature: "income_planning", enabled: true, hidden: false, requiredPlan: "Premier" }],
    },
    monthName: "July 2026", today: "2026-07-17", quickSort: "amount_desc", quickSortOptions: { amount_desc: "Highest First" },
    totalBudgetPlanned: 1400, fixedTotal: 1200, variablePlanTotal: 650,
    quickCashRemainingIncome: 2500, quickCashRemainingExpenses: 1675, quickCashWeekChange: -250, quickCashWeekEndBalance: 1750,
    quickCashProjection: {
      endDate: "2026-07-31", endBalance: 2825,
      balanceAnchor: { balance: 2000, checkingBalance: 1800, accountCount: 1, checkingAccountCount: 1, usesCashAccounts: true, includedAccounts: [{ id: 7, name: "Household Checking", institution: "Clear Bank", accountType: "checking", balance: 1800, mask: "1234", cashProjectionRole: "auto" }] },
      lowestBalance: { date: "2026-07-24", balance: 950 },
    },
    cashProjectionAccountRows: [{ accountId: 7, name: "Household Checking", institution: "Clear Bank", accountType: "checking", balance: 1800, mask: "1234", role: "auto", included: true, statusLabel: "Included", statusClass: "badge-green", statusDetail: "Automatically included" }],
    quickWorksheetRows: [
      { name: "Rent", subtitle: "Fixed expense", timing: "Jul 20", category: "Housing", amount: 1200, actionLabel: "Edit", readonly: false, itemType: "fixed_expense", itemId: 11 },
      { name: "Repair", subtitle: "One-time expense", timing: "Jul 28", category: "Home", amount: 250, actionLabel: "Edit", readonly: true, itemType: "forecast_item", itemId: 13 },
    ],
    fixedItems: [{ id: 11, name: "Rent", amount: 1200, dueDay: 20, startDate: "2026-07-20", frequency: "monthly", daysOfWeek: null, secondDate: null, secondDayOfMonth: null, monthlyWeekNumbers: null, monthlyWeekday: null, categoryLabel: "Housing", isLoan: false, notes: null, monthlyAmount: 1200 }],
    variableItems: [{ id: 12, name: "Groceries", amount: 150, frequency: "weekly", useSpecificDate: false, specificDate: null, daysOfWeek: null, categoryLabel: "Groceries", notes: null, monthlyAmount: 650 }],
    forecastItems: [{ id: 13, itemDate: "2026-07-28", description: "Repair", amount: 250, itemType: "expense", categoryLabel: "Home", notes: null }],
    recurringTemplates: [{ id: 14, name: "Gym", amount: 50, itemType: "expense", frequency: "monthly", startDate: "2026-07-22", secondDate: null, daysOfWeek: null, secondDayOfMonth: null, monthlyWeekNumbers: null, monthlyWeekday: null, categoryLabel: "Health", notes: null, incomeReplacement: false, incomeBasis: null, incomeType: null, paycheckCadence: null, incomeNextPayDate: null, hourlyHoursPerWeek: 0, additionalIncomeAmount: 0, additionalIncomeFrequency: "annual", taxState: null, taxFilingStatus: null, includePayrollTaxes: false, monthlyAmount: 50 }],
    categoryLabelOptions: ["Housing", "Groceries", "Home", "Health"],
    profile: { householdName: "Parker Household", incomeAmount: 90000, incomeAmountDisplay: 90000, monthlyIncome: 6000, incomeBasis: "gross", incomeType: "salary", incomeFrequency: "semimonthly", paycheckCadence: "semimonthly", nextPayDate: "2026-07-20", paycheckSecondDate: "2026-07-31", paycheckDaysOfWeek: null, paycheckSecondDayOfMonth: 31, paycheckMonthlyWeekNumbers: null, paycheckMonthlyWeekday: null, hourlyHoursPerWeek: 40, additionalIncomeAmount: 0, additionalIncomeFrequency: "annual", taxState: "NC", taxFilingStatus: "married_joint", includePayrollTaxes: true, notes: "Summer plan" },
    planIncome: 6000,
    incomeTypeOptions: { salary: "Salary", hourly: "Hourly" }, incomeBasisOptions: { take_home: "Take-Home", gross: "Gross" }, paycheckCadenceOptions: { weekly: "Weekly", biweekly: "Every Two Weeks", semimonthly: "Twice Per Month", monthly: "Monthly" }, taxFilingStatusOptions: { married_joint: "Married Filing Jointly" }, stateOptions: { NC: "North Carolina" }, recurringFrequencyOptions: { weekly: "Weekly", biweekly: "Every Two Weeks", semimonthly: "Twice Per Month", monthly: "Monthly", quarterly: "Quarterly", annual: "Annual" }, weekdayOptions: { 0: "Monday", 1: "Tuesday", 2: "Wednesday", 3: "Thursday", 4: "Friday", 5: "Saturday", 6: "Sunday" }, monthlyWeekOptions: { 1: "First", 2: "Second", 3: "Third", 4: "Fourth", 5: "Last" },
    ...overrides,
  };
}

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), { status, headers: { "content-type": "application/json" } });
}

describe("MonthlyQuickPlanningWorkspace", () => {
  beforeEach(() => { navigation.push.mockReset(); navigation.replace.mockReset(); navigation.refresh.mockReset(); vi.restoreAllMocks(); });

  it("refreshes explicitly, then renders the cash bridge, accounts, worksheet, and active navigation", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(jsonResponse({ synced: 0, errors: [] })).mockResolvedValueOnce(jsonResponse(view()));
    render(<MonthlyQuickPlanningWorkspace query={query} />);

    expect(await screen.findByRole("heading", { name: "Quick Planning", level: 1 })).toBeDefined();
    expect(screen.getByText("Current Operating Cash")).toBeDefined();
    expect(screen.getByText("Projected Month-End Cash")).toBeDefined();
    expect(screen.getByText("Household Checking · 1234: +$1,800")).toBeDefined();
    expect(screen.getByRole("spinbutton", { name: "Planned cash for Rent" })).toBeDefined();
    expect(screen.getByRole("link", { name: "Quick Planning" }).getAttribute("class")).toContain("active");
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/plaid-items/refresh-stale");
    expect(String(fetchMock.mock.calls[1]?.[0])).toContain("/api/monthly-plan?section=tools");
  });

  it("saves an amount-only worksheet edit and reloads without another Plaid refresh", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse({ synced: 0, errors: [] }))
      .mockResolvedValueOnce(jsonResponse(view()))
      .mockResolvedValueOnce(jsonResponse({ itemId: 11, monthlyAmount: 1250 }))
      .mockResolvedValueOnce(jsonResponse(view({ quickWorksheetRows: [{ ...view().quickWorksheetRows[0], amount: 1250 }, view().quickWorksheetRows[1]] })));
    render(<MonthlyQuickPlanningWorkspace query={query} />);
    const amount = await screen.findByRole("spinbutton", { name: "Planned cash for Rent" });
    fireEvent.change(amount, { target: { value: "1250" } });
    fireEvent.submit(amount.closest("form") as HTMLFormElement);

    await waitFor(() => expect(screen.getByText("Rent updated.")).toBeDefined());
    expect(fetchMock.mock.calls[2]?.[0]).toBe("/api/fixed-expenses/11");
    expect(JSON.parse(String(fetchMock.mock.calls[2]?.[1]?.body))).toEqual({ monthlyTarget: 1250 });
    expect(fetchMock.mock.calls[3]?.[0]).toBe("/api/monthly-plan?section=tools");
    expect(fetchMock).toHaveBeenCalledTimes(4);
  });

  it("opens the fixed-expense editor and posts the canonical full resource", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse({ synced: 0, errors: [] }))
      .mockResolvedValueOnce(jsonResponse(view()))
      .mockResolvedValueOnce(jsonResponse({ itemId: 21, name: "Insurance", monthlyAmount: 100 }, 201))
      .mockResolvedValueOnce(jsonResponse(view()));
    render(<MonthlyQuickPlanningWorkspace query={query} />);
    fireEvent.click(await screen.findByRole("button", { name: "Fixed Expense" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Expense Name" }), { target: { value: "Insurance" } });
    fireEvent.change(screen.getByRole("spinbutton", { name: "Amount For Selected Cadence" }), { target: { value: "100" } });
    fireEvent.click(screen.getByRole("button", { name: "Add Fixed Expense" }));

    await waitFor(() => expect(screen.getByText("Fixed expense saved.")).toBeDefined());
    expect(fetchMock.mock.calls[2]?.[0]).toBe("/api/fixed-expenses");
    expect(JSON.parse(String(fetchMock.mock.calls[2]?.[1]?.body))).toMatchObject({ name: "Insurance", amount: 100, frequency: "monthly", startDate: "2026-07-17" });
  });

  it("exposes and preserves recurring monthly weekday patterns on a full edit", async () => {
    const recurring = { ...view().recurringTemplates[0], monthlyWeekNumbers: "1,3", monthlyWeekday: 1 };
    const recurringView = view({
      recurringTemplates: [recurring],
      quickWorksheetRows: [{ name: "Gym", subtitle: "Recurring expense", timing: "Monthly", category: "Health", amount: 50, actionLabel: "Edit", readonly: false, itemType: "recurring_template", itemId: 14 }],
    });
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse({ synced: 0, errors: [] }))
      .mockResolvedValueOnce(jsonResponse(recurringView))
      .mockResolvedValueOnce(jsonResponse({ templateId: 14, name: "Gym", monthlyAmount: 50 }))
      .mockResolvedValueOnce(jsonResponse(recurringView));
    render(<MonthlyQuickPlanningWorkspace query={query} />);

    fireEvent.click(await screen.findByRole("button", { name: "Edit" }));
    const editor = within(screen.getByRole("dialog"));
    expect((editor.getByRole("combobox", { name: "Weekday Pattern" }) as HTMLSelectElement).value).toBe("1");
    expect((editor.getByRole("checkbox", { name: "First" }) as HTMLInputElement).checked).toBe(true);
    expect((editor.getByRole("checkbox", { name: "Third" }) as HTMLInputElement).checked).toBe(true);
    fireEvent.click(editor.getByRole("button", { name: "Save Recurring Item" }));

    await waitFor(() => expect(screen.getByText("Recurring item saved.")).toBeDefined());
    expect(JSON.parse(String(fetchMock.mock.calls[2]?.[1]?.body))).toMatchObject({
      recurringMonthlyWeekNumbers: [1, 3], recurringMonthlyWeekday: 1,
    });
  });

  it("keeps a shared household viewer read-only while preserving the cash information", async () => {
    const viewer = view({ session: { ...view().session, primaryAccountHolder: false, subject: { ...view().session.subject, id: 9, subjectType: "household_member", email: "viewer@example.com", displayName: "Taylor Viewer", firstName: "Taylor", avatarInitial: "T", householdRole: "viewer" } } });
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(jsonResponse({ message: "View only" }, 403)).mockResolvedValueOnce(jsonResponse(viewer));
    render(<MonthlyQuickPlanningWorkspace query={query} />);

    expect(await screen.findByText("You have view-only household access. Planning amounts and settings are read-only.")).toBeDefined();
    expect(screen.getByText("Projected Month-End Cash")).toBeDefined();
    expect(screen.queryByRole("spinbutton", { name: "Planned cash for Rent" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Fixed Expense" })).toBeNull();
    fireEvent.click(screen.getByText("Operating Cash Accounts"));
    expect(screen.queryByRole("button", { name: "Save" })).toBeNull();
  });
});
