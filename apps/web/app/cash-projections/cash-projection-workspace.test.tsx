import type { CashProjectionView, MonthlyQuickPlanningView } from "@clearpath/validation";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CashProjectionWorkspace, type CashProjectionQuery } from "./cash-projection-workspace";

const navigation = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }));
vi.mock("next/navigation", () => ({ usePathname: () => "/cash-projections", useRouter: () => navigation }));
vi.mock("qrcode", () => ({ default: { toDataURL: vi.fn().mockResolvedValue("data:image/png;base64,qr") } }));

const query: CashProjectionQuery = { month: "2026-07", horizon: "week", view: "calendar", startDate: "", endDate: "" };

function event(source = "one_time", sourceId: number | string | null = 13) {
  return { date: "2026-07-18", description: source === "one_time" ? "Car repair" : "Paycheck", amount: source === "one_time" ? 250 : 2000, itemType: source === "one_time" ? "expense" : "income", source, categoryLabel: source === "one_time" ? "Home" : "Income", notes: null, sourceId, signedAmount: source === "one_time" ? -250 : 2000, accountName: null, pending: false };
}

function day() {
  return { date: "2026-07-18", day: 18, weekday: "Saturday", isToday: true, isPast: false, events: [event()], actualEvents: [], scheduledEvents: [event()], actualBalance: 1800, balanceBasis: "Projected", netChange: -250, actualChange: 0, scheduledChange: -250, endingBalance: 1550 };
}

function graph() {
  return { points: "0,20 100,40", zeroAxisPct: 90, showZeroLine: true, minValue: 0, maxValue: 2000, monthMarkers: [], pointRows: [{ xPct: 0, yPct: 20, dateLabel: "Jul 18", balance: 1800, balanceBasis: "Actual" }] };
}

function anchor() {
  return { date: "2026-07-18", balance: 1800, checkingBalance: 1800, accountCount: 1, checkingAccountCount: 1, includedAccounts: [{ id: 9, name: "Main Checking", institution: "Primary Bank", accountType: "checking", balance: 1800, mask: "1234", cashProjectionRole: "auto" }], usesCashAccounts: true };
}

function period() {
  return { month: "2026-07-01", monthLabel: "July 2026", startDate: "2026-07-18", endDate: "2026-07-24", startBalance: 1800, endBalance: 1550, balanceAnchor: anchor(), lowestBalance: { date: "2026-07-24", balance: 1550 }, highestBalance: { date: "2026-07-18", balance: 1800 }, days: [day()], weeks: [], calendarCells: [day()], events: [event()], trend: { currentVariableSpend: 325, plannedVariableSpend: 800, averageFirstHalfShare: .48, affectsProjection: false, message: "Variable spending is running near plan." }, graph: graph() };
}

function cashView(overrides: Partial<CashProjectionView> = {}): CashProjectionView {
  return {
    horizon: "week", view: "calendar", projection: period(),
    projectionRange: { startMonth: "2026-07-01", startDate: "2026-07-18", endDate: "2026-07-24", months: 0, projections: [period()], days: [day()], events: [event()], startBalance: 1800, endBalance: 1550, balanceAnchor: anchor(), lowestBalance: { date: "2026-07-24", balance: 1550 }, highestBalance: { date: "2026-07-18", balance: 1800 }, graph: graph() },
    previousMonth: "2026-06-01", nextMonth: "2026-08-01", customStart: "2026-07-18", customEnd: "2026-08-17", customMinDate: "2026-01-18", customMaxDate: "2027-01-18", projectionMinMonth: "2026-01", projectionMaxMonth: "2027-01",
    accountRows: [{ accountId: 9, name: "Main Checking", institution: "Primary Bank", accountType: "checking", balance: 1800, mask: "1234", role: "auto", included: true, statusLabel: "Included", statusClass: "badge-green", statusDetail: "Primary operating cash account" }],
    detectedRecurring: [{ detectionKey: "merchant:fitness", name: "Local Fitness", amount: 45, frequency: "monthly", startDate: "2026-08-01", secondDayOfMonth: null, categoryLabel: "Fitness", notes: null, lastSeen: "2026-07-01" }], ignoredRecurring: [],
    calendarFeed: { enabled: false, feedUrl: null, webcalUrl: null, googleUrl: null, generatedAt: null, historyMonths: 3 }, refresh: null,
    ...overrides,
  };
}

function planView(overrides: Partial<MonthlyQuickPlanningView> = {}): MonthlyQuickPlanningView {
  return {
    session: { ownerUserId: 1, householdName: "Parker Household", selectedPlan: "premium", billingStatus: "active", planDisplayName: "Premier", primaryAccountHolder: true, subject: { id: 1, subjectType: "user", email: "parker@example.com", displayName: "Parker User", firstName: "Parker", avatarInitial: "P", householdRole: null }, featureAccess: [{ feature: "cash_projection", enabled: true, hidden: false, requiredPlan: "Premier" }] },
    monthName: "July 2026", today: "2026-07-18", quickSort: "amount_desc", quickSortOptions: {}, totalBudgetPlanned: 1400, fixedTotal: 1200, variablePlanTotal: 650, quickCashRemainingIncome: 2500, quickCashRemainingExpenses: 1675, quickCashWeekChange: -250, quickCashWeekEndBalance: 1550, quickCashProjection: null,
    cashProjectionAccountRows: [], quickWorksheetRows: [],
    fixedItems: [{ id: 11, name: "Rent", amount: 1200, dueDay: 20, startDate: "2026-07-20", frequency: "monthly", daysOfWeek: null, secondDate: null, secondDayOfMonth: null, monthlyWeekNumbers: null, monthlyWeekday: null, categoryLabel: "Housing", isLoan: false, notes: null, monthlyAmount: 1200 }],
    variableItems: [], forecastItems: [{ id: 13, itemDate: "2026-07-18", description: "Car repair", amount: 250, itemType: "expense", categoryLabel: "Home", notes: null }],
    recurringTemplates: [{ id: 14, name: "Gym", amount: 50, itemType: "expense", frequency: "monthly", startDate: "2026-07-22", secondDate: null, daysOfWeek: null, secondDayOfMonth: null, monthlyWeekNumbers: null, monthlyWeekday: null, categoryLabel: "Health", notes: null, incomeReplacement: false, incomeBasis: null, incomeType: null, paycheckCadence: null, incomeNextPayDate: null, hourlyHoursPerWeek: 0, additionalIncomeAmount: 0, additionalIncomeFrequency: "annual", taxState: null, taxFilingStatus: null, includePayrollTaxes: false, monthlyAmount: 50 }],
    categoryLabelOptions: ["Home", "Health", "Housing", "Fitness"],
    profile: { householdName: "Parker Household", incomeAmount: 90000, incomeAmountDisplay: 90000, monthlyIncome: 6000, incomeBasis: "gross", incomeType: "salary", incomeFrequency: "semimonthly", paycheckCadence: "semimonthly", nextPayDate: "2026-07-20", paycheckSecondDate: "2026-07-31", paycheckDaysOfWeek: null, paycheckSecondDayOfMonth: 31, paycheckMonthlyWeekNumbers: null, paycheckMonthlyWeekday: null, hourlyHoursPerWeek: 40, additionalIncomeAmount: 0, additionalIncomeFrequency: "annual", taxState: "NC", taxFilingStatus: "married_joint", includePayrollTaxes: true, notes: null }, planIncome: 6000,
    incomeTypeOptions: {}, incomeBasisOptions: {}, paycheckCadenceOptions: {}, taxFilingStatusOptions: {}, stateOptions: {}, recurringFrequencyOptions: { weekly: "Weekly", biweekly: "Every Two Weeks", semimonthly: "Twice Per Month", monthly: "Monthly", quarterly: "Quarterly", annual: "Annual" }, weekdayOptions: { 0: "Monday", 1: "Tuesday", 2: "Wednesday", 3: "Thursday", 4: "Friday", 5: "Saturday", 6: "Sunday" }, monthlyWeekOptions: { 1: "First", 2: "Second", 3: "Third", 4: "Fourth", 5: "Last" },
    ...overrides,
  };
}

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), { status, headers: { "content-type": "application/json" } });
}

describe("CashProjectionWorkspace", () => {
  beforeEach(() => { navigation.push.mockReset(); navigation.replace.mockReset(); navigation.refresh.mockReset(); vi.restoreAllMocks(); });

  it("renders the Flask-parity projection without an automatic Plaid refresh", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(jsonResponse(cashView())).mockResolvedValueOnce(jsonResponse(planView()));

    render(<CashProjectionWorkspace query={query} />);

    expect(await screen.findByRole("heading", { name: "Cash Balance Projections", level: 1 })).toBeDefined();
    expect(screen.getByText("Current Operating Cash")).toBeDefined();
    expect(screen.getByRole("heading", { name: "July 2026" })).toBeDefined();
    expect(screen.getByText("Car repair")).toBeDefined();
    expect(screen.getByRole("link", { name: "Cash Balance Projections" }).getAttribute("class")).toContain("active");
    expect(fetchMock.mock.calls.map((call) => call[0])).toEqual(["/api/cash-projections?month=2026-07&horizon=week", "/api/monthly-plan?section=tools"]);
    expect(fetchMock.mock.calls.some((call) => String(call[0]).includes("refresh"))).toBe(false);
  });

  it("persists a non-custom horizon explicitly before navigating", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(jsonResponse(cashView())).mockResolvedValueOnce(jsonResponse(planView())).mockResolvedValueOnce(jsonResponse({ defaultHorizon: "3m" }));
    render(<CashProjectionWorkspace query={query} />);

    fireEvent.change(await screen.findByRole("combobox", { name: "Time Horizon" }), { target: { value: "3m" } });

    await waitFor(() => expect(navigation.push).toHaveBeenCalledWith("/cash-projections?month=2026-07&horizon=3m"));
    expect(fetchMock.mock.calls[2]?.[0]).toBe("/api/cash-projections/preferences");
    expect(JSON.parse(String(fetchMock.mock.calls[2]?.[1]?.body))).toEqual({ defaultHorizon: "3m" });
  });

  it("refreshes balances only from the explicit command and surfaces the result", async () => {
    const refreshed = cashView({ refresh: { synced: 1, errors: [] }, projectionRange: { ...cashView().projectionRange, balanceAnchor: { ...anchor(), balance: 1950 } } });
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(jsonResponse(cashView())).mockResolvedValueOnce(jsonResponse(planView())).mockResolvedValueOnce(jsonResponse(refreshed));
    render(<CashProjectionWorkspace query={query} />);

    fireEvent.click(await screen.findByRole("button", { name: "Refresh Balances" }));

    expect(await screen.findByText("Refreshed 1 connected item.")).toBeDefined();
    expect(fetchMock.mock.calls[2]?.[0]).toBe("/api/cash-projections/refresh");
    expect(JSON.parse(String(fetchMock.mock.calls[2]?.[1]?.body))).toMatchObject({ month: "2026-07", horizon: "week", view: "calendar" });
  });

  it("edits a one-time schedule through the canonical forecast resource", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse(cashView())).mockResolvedValueOnce(jsonResponse(planView()))
      .mockResolvedValueOnce(jsonResponse({ itemId: 13 })).mockResolvedValueOnce(jsonResponse(cashView())).mockResolvedValueOnce(jsonResponse(planView()));
    render(<CashProjectionWorkspace query={query} />);

    fireEvent.click(await screen.findByRole("button", { name: "Edit Schedule" }));
    const dialog = within(screen.getByRole("dialog"));
    fireEvent.change(dialog.getByRole("textbox", { name: "Description" }), { target: { value: "Transmission repair" } });
    fireEvent.change(dialog.getByRole("combobox", { name: "Type" }), { target: { value: "income" } });
    fireEvent.click(dialog.getByRole("button", { name: "Save Planned Item" }));

    await waitFor(() => expect(screen.getByText("Planned cash item updated.")).toBeDefined());
    expect(fetchMock.mock.calls[2]?.[0]).toBe("/api/forecast-items/13");
    expect(JSON.parse(String(fetchMock.mock.calls[2]?.[1]?.body))).toMatchObject({ description: "Transmission repair", itemType: "income", amount: 250 });
  });

  it("keeps shared viewers read-only while retaining all projection views", async () => {
    const viewerPlan = planView({ session: { ...planView().session, primaryAccountHolder: false, subject: { ...planView().session.subject, id: 8, subjectType: "household_member", email: "viewer@example.com", displayName: "Taylor Viewer", firstName: "Taylor", avatarInitial: "T", householdRole: "viewer" } } });
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(jsonResponse(cashView())).mockResolvedValueOnce(jsonResponse(viewerPlan));
    render(<CashProjectionWorkspace query={query} />);

    expect(await screen.findByText("You have view-only household access. Projection settings and schedules are read-only.")).toBeDefined();
    expect(screen.queryByRole("button", { name: "Refresh Balances" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Edit Schedule" })).toBeNull();
    fireEvent.click(screen.getByText("Operating Cash Accounts"));
    expect(screen.queryByRole("button", { name: "Save" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Graph" }));
    expect(navigation.push).toHaveBeenCalledWith("/cash-projections?month=2026-07&horizon=week&view=graph");
  });
});
