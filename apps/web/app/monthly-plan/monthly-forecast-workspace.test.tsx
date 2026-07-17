import type { MonthlyForecastView } from "@clearpath/validation";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { MonthlyForecastWorkspace } from "./monthly-forecast-workspace";

const navigation = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }));
vi.mock("next/navigation", () => ({ usePathname: () => "/monthly-plan", useRouter: () => navigation }));

function movement(index: number) {
  return {
    date: `2026-07-${String(18 + index).padStart(2, "0")}`,
    description: index === 0 ? "Tax refund" : `Planned item ${index + 1}`,
    amount: 400 - index * 25,
    itemType: index === 0 ? "income" as const : "expense" as const,
    source: index === 0 ? "one_time" : "recurring",
    sourceId: 30 + index,
    categoryLabel: index === 0 ? "Income" : "Other",
    notes: null,
  };
}

function month(monthStart: string, monthName: string, plannedBuffer: number, endingCash: number, movements = [movement(0)]) {
  return {
    monthStart,
    monthName,
    baselineIncome: 4000,
    fixedExpenses: 1100,
    plannedSavings: 300,
    plannedDebt: 200,
    plannedTaxes: 500,
    plannedRetirement: 200,
    plannedVariable: 700,
    plannedIncome: 400,
    plannedExpenses: 600,
    oneTimeIncome: 400,
    oneTimeExpenses: 600,
    forecastIncomeTotal: 4800,
    forecastExpenseTotal: 3600,
    plannedBuffer,
    startingCash: 2500,
    endingCash,
    forecastItems: movements,
  };
}

function view(overrides: Partial<MonthlyForecastView> = {}): MonthlyForecastView {
  return {
    session: {
      ownerUserId: 1,
      householdName: "Parker Household",
      selectedPlan: "premium",
      billingStatus: "active",
      planDisplayName: "Premier",
      primaryAccountHolder: true,
      subject: { id: 1, subjectType: "user", email: "parker@example.com", displayName: "Parker User", firstName: "Parker", avatarInitial: "P", householdRole: null },
      featureAccess: [{ feature: "cash_projection", enabled: true, hidden: false, requiredPlan: "Premier" }],
    },
    today: "2026-07-17",
    forecastMonths: [
      month("2026-07-01", "July 2026", 1200, 3700, Array.from({ length: 6 }, (_, index) => movement(index))),
      month("2026-08-01", "August 2026", 250, 3950),
      month("2026-09-01", "September 2026", -50, 3900),
    ],
    forecastItems: [
      { id: 31, itemDate: "2026-07-20", description: "Tax refund", amount: 400, itemType: "income", categoryLabel: "Income", notes: null },
      { id: 32, itemDate: "2026-07-28", description: "Car repair", amount: 600, itemType: "expense", categoryLabel: "Auto", notes: "Expected quote" },
    ],
    categoryLabelOptions: ["Auto", "Income", "Other"],
    ...overrides,
  };
}

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), { status, headers: { "content-type": "application/json" } });
}

describe("MonthlyForecastWorkspace", () => {
  beforeEach(() => {
    navigation.push.mockReset();
    navigation.replace.mockReset();
    navigation.refresh.mockReset();
    vi.restoreAllMocks();
  });

  it("refreshes explicitly and renders Flask-parity month statuses, movement, and active navigation", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse({ synced: 0, errors: [] }))
      .mockResolvedValueOnce(jsonResponse(view()));

    render(<MonthlyForecastWorkspace />);

    expect(await screen.findByRole("heading", { name: "3-Month Forecast", level: 1 })).toBeDefined();
    expect(screen.getByText("Healthy")).toBeDefined();
    expect(screen.getByText("Watch")).toBeDefined();
    expect(screen.getByText("Tight")).toBeDefined();
    expect(screen.getByText("+ 1 more planned item")).toBeDefined();
    expect(screen.getByRole("link", { name: "3-Month Forecast" }).getAttribute("class")).toContain("active");
    expect(screen.getByRole("link", { name: "Open Cash Balance Projections" }).getAttribute("href")).toBe("/cash-projections");
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/plaid-items/refresh-stale");
    expect(fetchMock.mock.calls[1]?.[0]).toBe("/api/monthly-plan?section=forecast");
  });

  it("creates a one-time expense and reloads without a second Plaid refresh", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse({ synced: 0, errors: [] }))
      .mockResolvedValueOnce(jsonResponse(view()))
      .mockResolvedValueOnce(jsonResponse({ itemId: 40, description: "Annual premium", amount: 900 }, 201))
      .mockResolvedValueOnce(jsonResponse(view()));
    render(<MonthlyForecastWorkspace />);

    fireEvent.change(await screen.findByRole("textbox", { name: "Description" }), { target: { value: "Annual premium" } });
    fireEvent.change(screen.getByRole("spinbutton", { name: "Amount" }), { target: { value: "900" } });
    fireEvent.click(screen.getByRole("button", { name: "Add One-Time Expense" }));

    await waitFor(() => expect(screen.getByText("One-time expense added.")).toBeDefined());
    expect(fetchMock.mock.calls[2]?.[0]).toBe("/api/forecast-items");
    expect(JSON.parse(String(fetchMock.mock.calls[2]?.[1]?.body))).toMatchObject({
      itemDate: "2026-07-17", description: "Annual premium", amount: 900, itemType: "expense",
    });
    expect(fetchMock.mock.calls[3]?.[0]).toBe("/api/monthly-plan?section=forecast");
    expect(fetchMock).toHaveBeenCalledTimes(4);
  });

  it("edits the expense resource from the forecast list", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse({ synced: 0, errors: [] }))
      .mockResolvedValueOnce(jsonResponse(view()))
      .mockResolvedValueOnce(jsonResponse({ itemId: 32, description: "Roof repair", amount: 700 }))
      .mockResolvedValueOnce(jsonResponse(view()));
    render(<MonthlyForecastWorkspace />);

    fireEvent.click(await screen.findByRole("button", { name: "Edit" }));
    const editor = within(screen.getByRole("dialog"));
    fireEvent.change(editor.getByRole("textbox", { name: "Description" }), { target: { value: "Roof repair" } });
    fireEvent.change(editor.getByRole("spinbutton", { name: "Amount" }), { target: { value: "700" } });
    fireEvent.click(editor.getByRole("button", { name: "Save One-Time Item" }));

    await waitFor(() => expect(screen.getByText("One-time forecast item updated.")).toBeDefined());
    expect(fetchMock.mock.calls[2]?.[0]).toBe("/api/forecast-items/32");
    expect(fetchMock.mock.calls[2]?.[1]?.method).toBe("PATCH");
    expect(JSON.parse(String(fetchMock.mock.calls[2]?.[1]?.body))).toMatchObject({ description: "Roof repair", amount: 700 });
  });

  it("deletes a confirmed one-time expense and reloads the forecast", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse({ synced: 0, errors: [] }))
      .mockResolvedValueOnce(jsonResponse(view()))
      .mockResolvedValueOnce(jsonResponse({ deletedItemId: 32 }))
      .mockResolvedValueOnce(jsonResponse(view({ forecastItems: [] })));
    render(<MonthlyForecastWorkspace />);

    fireEvent.click(await screen.findByRole("button", { name: "Edit" }));
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Delete" }));

    await waitFor(() => expect(screen.getByText("One-time forecast item removed.")).toBeDefined());
    expect(fetchMock.mock.calls[2]?.[0]).toBe("/api/forecast-items/32");
    expect(fetchMock.mock.calls[2]?.[1]?.method).toBe("DELETE");
    expect(JSON.parse(String(fetchMock.mock.calls[2]?.[1]?.body))).toEqual({ confirm: true });
  });

  it("keeps a shared viewer read-only while preserving all forecast months", async () => {
    const viewer = view({
      session: {
        ...view().session,
        primaryAccountHolder: false,
        subject: { ...view().session.subject, id: 9, subjectType: "household_member", email: "viewer@example.com", displayName: "Taylor Viewer", firstName: "Taylor", avatarInitial: "T", householdRole: "viewer" },
      },
    });
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse({ message: "View only" }, 403))
      .mockResolvedValueOnce(jsonResponse(viewer));
    render(<MonthlyForecastWorkspace />);

    expect(await screen.findByText("You have view-only household access. Forecast items are read-only.")).toBeDefined();
    expect(screen.getByRole("heading", { name: "July 2026" })).toBeDefined();
    expect(screen.getByRole("heading", { name: "September 2026" })).toBeDefined();
    expect(screen.queryByRole("button", { name: "Add One-Time Expense" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Edit" })).toBeNull();
  });
});
