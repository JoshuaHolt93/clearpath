import type { MonthlyIncomePlanningView } from "@clearpath/validation";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { MonthlyIncomePlanningWorkspace } from "./monthly-income-planning-workspace";

const navigation = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }));
vi.mock("next/navigation", () => ({ usePathname: () => "/monthly-plan", useRouter: () => navigation }));

function view(overrides: Partial<MonthlyIncomePlanningView> = {}): MonthlyIncomePlanningView {
  return {
    session: {
      ownerUserId: 1,
      householdName: "Parker Household",
      selectedPlan: "premium",
      billingStatus: "active",
      planDisplayName: "Premier",
      primaryAccountHolder: true,
      subject: { id: 1, subjectType: "user", email: "parker@example.com", displayName: "Parker User", firstName: "Parker", avatarInitial: "P", householdRole: null },
      featureAccess: [{ feature: "income_planning", enabled: true, hidden: false, requiredPlan: "Premier" }],
    },
    today: "2026-07-17",
    profile: {
      householdName: "Parker Household",
      incomeAmount: 90000,
      incomeAmountDisplay: 90000,
      monthlyIncome: 7600,
      incomeBasis: "gross",
      incomeType: "salary",
      incomeFrequency: "semimonthly",
      paycheckCadence: "semimonthly",
      nextPayDate: "2026-07-16",
      paycheckSecondDate: "2026-07-31",
      paycheckDaysOfWeek: null,
      paycheckSecondDayOfMonth: 31,
      paycheckMonthlyWeekNumbers: null,
      paycheckMonthlyWeekday: null,
      hourlyHoursPerWeek: 40,
      additionalIncomeAmount: 1200,
      additionalIncomeFrequency: "annual",
      taxState: "NC",
      taxFilingStatus: "married_joint",
      includePayrollTaxes: true,
      notes: "Summer plan",
      taxAdditionalLabel: "County Tax",
      taxAdditionalType: "percent",
      taxAdditionalRate: 1.25,
      taxAdditionalMonthlyAmount: 0,
    },
    planIncome: 7600,
    futureIncomeTemplates: [{
      id: 21,
      name: "Fall Raise",
      amount: 96000,
      itemType: "income",
      frequency: "semimonthly",
      startDate: "2026-09-01",
      secondDate: "2026-09-30",
      daysOfWeek: null,
      secondDayOfMonth: 30,
      monthlyWeekNumbers: null,
      monthlyWeekday: null,
      categoryLabel: "Income",
      notes: "Promotion",
      incomeReplacement: true,
      incomeBasis: "gross",
      incomeType: "salary",
      paycheckCadence: "semimonthly",
      incomeNextPayDate: "2026-09-15",
      hourlyHoursPerWeek: 40,
      additionalIncomeAmount: 0,
      additionalIncomeFrequency: "annual",
      taxState: "NC",
      taxFilingStatus: "married_joint",
      includePayrollTaxes: true,
      monthlyAmount: 8000,
    }],
    taxEstimate: {
      annualGrossIncome: 91200,
      taxableIncome: 61200,
      federalIncomeTax: 7000,
      stateIncomeTax: 3200,
      socialSecurityTax: 5654.4,
      medicareTax: 1322.4,
      additionalMedicareTax: 0,
      additionalTaxLabel: "County Tax",
      additionalTaxType: "percent",
      additionalTaxRate: 1.25,
      additionalTaxAnnual: 1140,
      additionalTaxMonthly: 95,
      annualTotal: 18316.8,
      monthlyTotal: 1526.4,
      filingStatus: "married_joint",
      state: "NC",
      stateRate: 4.5,
      stateMethod: "Progressive",
      stateTaxableIncome: 66000,
      stateStandardDeduction: 25500,
      statePersonalExemption: 0,
      stateCredit: 0,
      stateBrackets: [[0, 0.045]],
      stateNote: "North Carolina estimate.",
      stateSourceUrl: "https://www.ncdor.gov/",
      federalBrackets: [[0, 23850, 0, 0.1], [23850, null, 2385, 0.12]],
      standardDeduction: 30000,
    },
    taxesEnabled: true,
    incomeTypeOptions: { salary: "Salary", hourly: "Hourly", bonus: "Bonus" },
    incomeBasisOptions: { take_home: "Take-Home Income", gross: "Gross Income" },
    paycheckCadenceOptions: { weekly: "Weekly", biweekly: "Every Two Weeks", semimonthly: "Twice Per Month", monthly: "Monthly" },
    taxFilingStatusOptions: { married_joint: "Married Filing Jointly" },
    stateOptions: { NC: "North Carolina" },
    recurringFrequencyOptions: { weekly: "Weekly", biweekly: "Every Two Weeks", semimonthly: "Twice Per Month", monthly: "Monthly", quarterly: "Quarterly", annual: "Annual" },
    weekdayOptions: { 0: "Monday", 1: "Tuesday", 2: "Wednesday", 3: "Thursday", 4: "Friday", 5: "Saturday", 6: "Sunday" },
    monthlyWeekOptions: { 1: "First", 2: "Second", 3: "Third", 4: "Fourth", 5: "Last" },
    ...overrides,
  };
}

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), { status, headers: { "content-type": "application/json" } });
}

function currentIncomePanel() {
  const heading = screen.getByRole("heading", { name: "Adjust Current Income" });
  const details = heading.closest("details");
  if (!details) throw new Error("Current income panel was not rendered.");
  fireEvent.click(details.querySelector("summary") as HTMLElement);
  return within(details);
}

function futureIncomePanel() {
  const heading = screen.getByRole("heading", { name: "Future Income Planning" });
  const section = heading.closest("section");
  if (!section) throw new Error("Future income panel was not rendered.");
  return within(section);
}

describe("MonthlyIncomePlanningWorkspace", () => {
  beforeEach(() => {
    navigation.push.mockReset();
    navigation.replace.mockReset();
    navigation.refresh.mockReset();
    vi.restoreAllMocks();
  });

  it("refreshes explicitly and renders current income, tax-aware math, future income, and navigation", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse(view()))
      .mockResolvedValueOnce(jsonResponse({ synced: 0, errors: [] }));
    render(<MonthlyIncomePlanningWorkspace />);

    expect(await screen.findByRole("heading", { name: "Income Planning", level: 1 })).toBeDefined();
    expect(screen.getByText("Fall Raise")).toBeDefined();
    expect(screen.getByText(/Replacement income starting Sep 1, 2026/)).toBeDefined();
    expect(screen.getByText("1 Scheduled")).toBeDefined();
    expect(screen.getByRole("link", { name: "Income Planning" }).getAttribute("class")).toContain("active");
    const current = currentIncomePanel();
    expect((current.getByLabelText(/Estimated Monthly Gross Income/) as HTMLInputElement).value).toBe("7600.00");
    // The page must render from saved data first; the Plaid refresh runs
    // afterwards so a slow sync cannot hold the loading screen up.
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain("/api/monthly-plan");
    await waitFor(() => expect(fetchMock.mock.calls.some((call) => String(call[0]).includes("refresh-stale"))).toBe(true));
  });

  it("saves the complete current-income baseline without bypassing the income-planning gate", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse(view()))
      .mockResolvedValueOnce(jsonResponse({ synced: 0, errors: [] }))
      .mockResolvedValueOnce(jsonResponse({ profile: {}, plan: { income: 8100 } }))
      .mockResolvedValueOnce(jsonResponse(view({ planIncome: 8100 })));
    render(<MonthlyIncomePlanningWorkspace />);

    await screen.findByRole("heading", { name: "Income Planning" });
    const current = currentIncomePanel();
    fireEvent.change(current.getAllByLabelText(/Annual Salary/)[0]!, { target: { value: "96000" } });
    fireEvent.click(current.getByRole("button", { name: "Save Income Plan" }));

    await waitFor(() => expect(screen.getByText("Income plan updated.")).toBeDefined());
    expect(fetchMock.mock.calls[2]?.[0]).toBe("/api/monthly-plan/baseline");
    const payload = JSON.parse(String(fetchMock.mock.calls[2]?.[1]?.body));
    expect(payload).toMatchObject({ incomeAmount: 96000, incomeBasis: "gross", incomeType: "salary", paycheckCadence: "semimonthly", section: "baseline" });
    expect(payload).not.toHaveProperty("baselineScope");
    expect(fetchMock.mock.calls[3]?.[0]).toBe("/api/monthly-plan?section=baseline");
    expect(fetchMock).toHaveBeenCalledTimes(4);
  });

  it("creates a future adjustment with the full Flask income schedule and clamps first pay to its start date", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse(view()))
      .mockResolvedValueOnce(jsonResponse({ synced: 0, errors: [] }))
      .mockResolvedValueOnce(jsonResponse({ id: 22, name: "Winter Contract" }, 201))
      .mockResolvedValueOnce(jsonResponse(view()));
    render(<MonthlyIncomePlanningWorkspace />);

    await screen.findByRole("heading", { name: "Income Planning" });
    const future = futureIncomePanel();
    expect((future.getByLabelText("First Pay Date") as HTMLInputElement).value).toBe("2026-07-17");
    fireEvent.change(future.getByLabelText("Adjustment Name"), { target: { value: "Winter Contract" } });
    fireEvent.change(future.getByLabelText("Adjustment Type"), { target: { value: "no" } });
    fireEvent.change(future.getByLabelText("Adjustment Start Date"), { target: { value: "2026-10-01" } });
    expect((future.getByLabelText("First Pay Date") as HTMLInputElement).value).toBe("2026-10-01");
    fireEvent.change(future.getByLabelText("Annual Salary"), { target: { value: "24000" } });
    fireEvent.click(future.getByRole("button", { name: "Add Income Adjustment" }));

    await waitFor(() => expect(screen.getByText("Income adjustment added.")).toBeDefined());
    const payload = JSON.parse(String(fetchMock.mock.calls[2]?.[1]?.body));
    expect(payload).toMatchObject({
      name: "Winter Contract", amount: 24000, itemType: "income", categoryLabel: "Income",
      incomeAdjustment: true, incomeReplacement: false, incomeBasis: "gross", incomeType: "salary",
      paycheckCadence: "semimonthly", incomeNextPayDate: "2026-10-01", incomeAmount: 24000,
      additionalIncomeAmount: 1200, additionalIncomeFrequency: "annual", taxState: "NC",
      taxFilingStatus: "married_joint", includePayrollTaxes: true,
    });
    expect(fetchMock.mock.calls[2]?.[0]).toBe("/api/recurring-templates");
    expect(fetchMock).toHaveBeenCalledTimes(4);
    expect((future.getByLabelText("Adjustment Name") as HTMLInputElement).value).toBe("");
    expect((future.getByLabelText("Annual Salary") as HTMLInputElement).value).toBe("90000");
  });

  it("edits and deletes a future adjustment through the recurring-template resource", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse(view()))
      .mockResolvedValueOnce(jsonResponse({ synced: 0, errors: [] }))
      .mockResolvedValueOnce(jsonResponse({ id: 21, name: "Fall Promotion" }))
      .mockResolvedValueOnce(jsonResponse(view()))
      .mockResolvedValueOnce(jsonResponse({ deletedTemplateId: 21 }))
      .mockResolvedValueOnce(jsonResponse(view({ futureIncomeTemplates: [] })));
    render(<MonthlyIncomePlanningWorkspace />);

    fireEvent.click(await screen.findByRole("button", { name: "Edit" }));
    let editor = within(screen.getByRole("dialog"));
    fireEvent.change(editor.getByLabelText("Adjustment Name"), { target: { value: "Fall Promotion" } });
    fireEvent.click(editor.getByRole("button", { name: "Save Adjustment" }));
    await waitFor(() => expect(screen.getByText("Income adjustment updated.")).toBeDefined());
    expect(fetchMock.mock.calls[2]?.[0]).toBe("/api/recurring-templates/21");
    expect(fetchMock.mock.calls[2]?.[1]?.method).toBe("PATCH");

    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    editor = within(screen.getByRole("dialog"));
    fireEvent.click(editor.getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(screen.getByText("Income adjustment removed.")).toBeDefined());
    expect(fetchMock.mock.calls[4]?.[0]).toBe("/api/recurring-templates/21");
    expect(fetchMock.mock.calls[4]?.[1]?.method).toBe("DELETE");
    expect(JSON.parse(String(fetchMock.mock.calls[4]?.[1]?.body))).toEqual({ confirm: true });
  });

  it("saves the tax worksheet through the core baseline path and keeps shared viewers read-only", async () => {
    const viewer = view({
      session: {
        ...view().session,
        primaryAccountHolder: false,
        subject: { ...view().session.subject, id: 9, subjectType: "household_member", email: "viewer@example.com", displayName: "Taylor Viewer", firstName: "Taylor", avatarInitial: "T", householdRole: "viewer" },
      },
    });
    const ownerFetch = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse(view()))
      .mockResolvedValueOnce(jsonResponse({ synced: 0, errors: [] }))
      .mockResolvedValueOnce(jsonResponse({ profile: {}, plan: { income: 7600 } }))
      .mockResolvedValueOnce(jsonResponse(view()));
    const ownerRender = render(<MonthlyIncomePlanningWorkspace />);

    await screen.findByRole("heading", { name: "Income Planning" });
    const current = currentIncomePanel();
    fireEvent.click(current.getByRole("button", { name: "Tax Planning Module" }));
    const taxes = within(screen.getByRole("dialog"));
    expect(taxes.getByText("$1,526")).toBeDefined();
    fireEvent.change(taxes.getByLabelText("Additional Tax Rate"), { target: { value: "2.5" } });
    fireEvent.click(taxes.getByRole("button", { name: "Save Tax Worksheet" }));
    await waitFor(() => expect(screen.getByText("Tax worksheet updated.")).toBeDefined());
    expect(JSON.parse(String(ownerFetch.mock.calls[2]?.[1]?.body))).toMatchObject({ baselineScope: "core", taxAdditionalLabel: "County Tax", taxAdditionalType: "percent", taxAdditionalRate: 2.5, section: "baseline" });
    ownerRender.unmount();

    ownerFetch.mockReset()
      .mockResolvedValueOnce(jsonResponse(viewer))
      .mockResolvedValueOnce(jsonResponse({ message: "View only" }, 403));
    render(<MonthlyIncomePlanningWorkspace />);
    expect(await screen.findByText("You have view-only household access. Income settings and adjustments are read-only.")).toBeDefined();
    expect(screen.queryByRole("button", { name: "Add Income Adjustment" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Edit" })).toBeNull();
    const viewerCurrent = currentIncomePanel();
    expect(viewerCurrent.queryByRole("button", { name: "Save Income Plan" })).toBeNull();
    expect(viewerCurrent.getByText("Shared viewers can review this income plan but cannot change it.")).toBeDefined();
  });
});
