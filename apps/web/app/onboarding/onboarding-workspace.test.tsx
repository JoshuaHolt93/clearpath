import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { OnboardingWorkspace } from "./onboarding-workspace";

const navigation = vi.hoisted(() => ({ push: vi.fn() }));

vi.mock("next/navigation", () => ({ useRouter: () => navigation }));
vi.mock("next/script", () => ({ default: () => null }));

function status(overrides: Record<string, unknown> = {}) {
  return {
    activeStep: "income",
    incomeReady: false,
    hasBank: true,
    setupComplete: false,
    profile: {
      householdName: "Parker Household",
      incomeAmount: 0,
      incomeAmountDisplay: 0,
      monthlyIncome: 0,
      incomeBasis: "take_home",
      incomeType: "salary",
      paycheckCadence: "monthly",
      nextPayDate: "2026-07-31",
      paycheckSecondDate: null,
      paycheckDaysOfWeek: null,
      paycheckMonthlyWeekNumbers: null,
      paycheckMonthlyWeekday: null,
      hourlyHoursPerWeek: 40,
      additionalIncomeAmount: 0,
      additionalIncomeFrequency: "annual",
      taxState: null,
      taxFilingStatus: "married_joint",
      includePayrollTaxes: true,
      notes: null,
    },
    today: "2026-07-16",
    plaidStatus: { ready: true, sdkInstalled: true, cryptoInstalled: true, hasCredentials: true, hasEncryptionKey: true, environment: "sandbox" },
    plaidItems: [{ id: 4, institutionName: "First Test Bank", status: "connected", lastSyncedAt: null }],
    transactions: [],
    categories: [{ id: 7, name: "Groceries", kind: "expense" }, { id: 8, name: "Income", kind: "income" }],
    autoCategorizedCount: 0,
    seededBudgetCount: 0,
    message: null,
    nextPath: null,
    incomeBasisOptions: { take_home: "Take-Home", gross: "Gross" },
    incomeTypeOptions: { salary: "Salary", hourly: "Hourly" },
    paycheckCadenceOptions: { monthly: "Monthly", semimonthly: "Twice Monthly" },
    recurringFrequencyOptions: { monthly: "Monthly", annual: "Annual" },
    weekdayOptions: { "0": "Monday", "1": "Tuesday" },
    monthlyWeekOptions: { "1": "First", "2": "Second" },
    taxFilingStatusOptions: { married_joint: "Married Filing Jointly" },
    stateOptions: { "": "Choose State", IN: "Indiana" },
    ...overrides,
  };
}

describe("OnboardingWorkspace", () => {
  beforeEach(() => {
    navigation.push.mockReset();
    vi.restoreAllMocks();
  });

  it("saves canonical income fields and advances to transaction review", async () => {
    const review = status({
      activeStep: "transactions",
      incomeReady: true,
      setupComplete: true,
      autoCategorizedCount: 1,
      message: "Your income plan is saved. Review a few transaction examples next.",
      transactions: [{ id: 12, displayMerchant: "Kroger", postedDate: "2026-07-15", amount: -63.45, accountName: "Checking", sourceName: null, categoryId: 7 }],
    });
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify(status()), { status: 200, headers: { "content-type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify(review), { status: 200, headers: { "content-type": "application/json" } }));
    render(<OnboardingWorkspace initialStep="income" />);

    expect(await screen.findByRole("heading", { name: "Set Your Income" })).toBeDefined();
    fireEvent.change(screen.getByLabelText("Paycheck Cadence"), { target: { value: "semimonthly" } });
    fireEvent.change(screen.getByLabelText("Second Pay Date"), { target: { value: "2026-08-15" } });
    fireEvent.change(screen.getByLabelText("Annual Salary"), { target: { value: "120000" } });
    fireEvent.click(screen.getByRole("button", { name: "Save Income And Continue" }));

    expect(await screen.findByRole("heading", { name: "Review A Few Transactions" })).toBeDefined();
    const submitted = JSON.parse(String(fetchMock.mock.calls[1]?.[1]?.body));
    expect(submitted).toMatchObject({
      income_amount: 120000,
      income_basis: "take_home",
      income_type: "salary",
      paycheck_cadence: "semimonthly",
      next_pay_date: "2026-07-31",
      second_date: "2026-08-15",
      include_payroll_taxes: true,
    });
    expect(window.location.search).toBe("?step=transactions");
  });

  it("saves a reviewed category and follows the completion destination", async () => {
    const review = status({
      activeStep: "transactions",
      incomeReady: true,
      setupComplete: true,
      transactions: [{ id: 12, displayMerchant: "Kroger", postedDate: "2026-07-15", amount: -63.45, accountName: "Checking", sourceName: null, categoryId: 7 }],
    });
    const complete = status({ ...review, message: "Initial budgets are ready.", seededBudgetCount: 2, nextPath: "/monthly-plan?section=budgets&onboarding=complete" });
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify(review), { status: 200, headers: { "content-type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ transactionId: 12, categoryId: 7 }), { status: 200, headers: { "content-type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify(complete), { status: 200, headers: { "content-type": "application/json" } }));
    render(<OnboardingWorkspace initialStep="transactions" />);

    expect(await screen.findByRole("heading", { name: "Review A Few Transactions" })).toBeDefined();
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(JSON.parse(String(fetchMock.mock.calls[1]?.[1]?.body))).toEqual({ category_id: 7 });

    fireEvent.click(screen.getByRole("button", { name: "Finish Setup" }));
    await waitFor(() => expect(navigation.push).toHaveBeenCalledWith("/monthly-plan?section=budgets&onboarding=complete"));
  });
});
