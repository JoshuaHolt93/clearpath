import assert from "node:assert/strict";
import test from "node:test";

import {
  amortizationSchedule,
  amortizationSummary,
  calculateDashboardMetricValues,
  calculateGoalProgress,
  calculateNetWorthSummary,
  estimateGoalTimeline,
  forecastBufferStatus,
  loanPlanScenarios,
  monthlyIncomeEstimate,
  monthlyizeIncomeAmount,
  monthsUntil,
  requiredExtraPaymentForDebtGoal,
  requiredMonthlyForGoal,
  retirementCashFlowContribution,
  retirementTaxableIncomeAdjustment,
  savingsGoalBudgetLabel,
  summarizeAnalyticsSnapshots,
} from "../src/index.ts";

const goal = {
  goalType: "savings",
  targetAmount: 1000,
  currentAmount: 200,
  monthlyContribution: 100,
  targetDate: "2026-09-14",
};

test("ports goal month and contribution math", () => {
  assert.equal(monthsUntil(goal.targetDate, "2026-07-14"), 2);
  assert.equal(requiredMonthlyForGoal(goal, "2026-07-14"), 400);
  assert.equal(estimateGoalTimeline(goal, "2026-07-14"), "About 8 months");
  assert.equal(
    estimateGoalTimeline({ ...goal, monthlyContribution: 0 }, "2026-07-14"),
    "Save $400/month to hit target date",
  );
  assert.equal(
    estimateGoalTimeline(
      { ...goal, targetAmount: 5, currentAmount: 0, monthlyContribution: 0 },
      "2026-07-14",
    ),
    "Save $2/month to hit target date",
  );
});

test("ports savings category rules", () => {
  assert.equal(savingsGoalBudgetLabel("College Tuition"), "Education Savings");
  assert.equal(savingsGoalBudgetLabel("Roth IRA"), "Retirement (401k, IRA)");
  assert.equal(savingsGoalBudgetLabel("Brokerage Investing"), "Investments");
  assert.equal(savingsGoalBudgetLabel("Rainy Day"), "Emergency Fund");
});

test("ports retirement cash-flow and taxable-income adjustments", () => {
  const grossProfile = {
    retirementEnabled: true,
    retirementHasEmployerPlan: true,
    retirementEmployerWithheld: true,
    retirementMonthlyContribution: 500,
    retirementPersonalMonthlyContribution: 200,
    incomeBasis: "gross",
  };
  assert.equal(retirementCashFlowContribution(grossProfile), 700);
  assert.equal(retirementTaxableIncomeAdjustment(grossProfile), 6000);

  assert.equal(retirementCashFlowContribution({ ...grossProfile, incomeBasis: "take_home" }), 200);
  assert.equal(retirementTaxableIncomeAdjustment({ ...grossProfile, retirementHasEmployerPlan: false }), 0);
  assert.equal(retirementCashFlowContribution({ ...grossProfile, retirementEnabled: false }), 0);
  assert.equal(retirementCashFlowContribution({ ...grossProfile, retirementMonthlyContribution: -50 }), 200);
});

test("ports dashboard safe-to-spend and on-track thresholds", () => {
  const input = {
    plannedIncome: 5000,
    monthlyTax: 0,
    fixedExpenses: 1800,
    plannedSavings: 0,
    plannedDebtPayment: 0,
    retirementContribution: 0,
    loanExtraPayment: 0,
    variableSpend: 200,
    recordedIncome: 5000,
    totalExpenses: 2000,
    safeToSpendTarget: 3200,
    dayOfMonth: 15,
    daysInMonth: 31,
  };
  const metrics = calculateDashboardMetricValues(input);
  assert.equal(metrics.safeToSpend, 3000);
  assert.equal(metrics.netCashFlow, 3000);
  assert.ok(Math.abs(metrics.expectedVariableSpend - (3200 * 15) / 31) < 1e-9);
  assert.equal(metrics.onTrackStatus, "green");
  assert.equal(calculateDashboardMetricValues({ ...input, variableSpend: 1700 }).onTrackStatus, "yellow");
  assert.equal(calculateDashboardMetricValues({ ...input, variableSpend: 1900 }).onTrackStatus, "red");
});

test("ports Flask three-month forecast buffer thresholds", () => {
  assert.deepEqual(forecastBufferStatus(-1), { key: "tight", label: "Tight" });
  assert.deepEqual(forecastBufferStatus(0), { key: "watch", label: "Watch" });
  assert.deepEqual(forecastBufferStatus(299.99), { key: "watch", label: "Watch" });
  assert.deepEqual(forecastBufferStatus(300), { key: "healthy", label: "Healthy" });
});

test("ports Flask Income Planning monthly estimates", () => {
  assert.equal(monthlyizeIncomeAmount(1200, "annual"), 100);
  assert.equal(monthlyizeIncomeAmount(300, "quarterly"), 100);
  assert.equal(monthlyizeIncomeAmount(2000, "semimonthly"), 4000);
  assert.ok(Math.abs(monthlyizeIncomeAmount(2000, "biweekly") - (2000 * 26) / 12) < 1e-9);
  assert.equal(monthlyizeIncomeAmount(25, "hourly", 40), (25 * 40 * 52) / 12);
  assert.equal(monthlyizeIncomeAmount(500, "irregular"), 500);

  assert.equal(monthlyIncomeEstimate({
    incomeAmount: 90000,
    incomeType: "salary",
    paycheckCadence: "semimonthly",
    hourlyHoursPerWeek: 40,
    additionalIncomeAmount: 1200,
    additionalIncomeFrequency: "annual",
  }), 7600);
  assert.equal(monthlyIncomeEstimate({
    incomeAmount: 30,
    incomeType: "hourly",
    paycheckCadence: "weekly",
    hourlyHoursPerWeek: 35,
    additionalIncomeAmount: 0,
    additionalIncomeFrequency: "annual",
  }), (30 * 35 * 52) / 12);
  assert.equal(monthlyIncomeEstimate({
    incomeAmount: 2500,
    incomeType: "bonus",
    paycheckCadence: "quarterly",
    hourlyHoursPerWeek: 40,
    additionalIncomeAmount: 0,
    additionalIncomeFrequency: "annual",
  }), (2500 * 4) / 12);
});

test("ports Flask net-worth aggregation", () => {
  assert.deepEqual(
    calculateNetWorthSummary(
      [
        { balance: 10000, isLiability: false },
        { balance: 2000, isLiability: true },
      ],
      [
        { principalBalance: 100000, collateralValue: 150000 },
        { principalBalance: 5000, collateralValue: 0 },
      ],
      [3000],
    ),
    {
      assets: 60000,
      liabilities: 110000,
      loanBalances: 105000,
      collateralAssets: 50000,
      collateralValue: 150000,
      securedLoanEquity: 50000,
      securedNegativeEquity: 0,
      securedLoanBalances: 100000,
      unsecuredLoanBalances: 5000,
      debtGoals: 3000,
      netWorth: -50000,
    },
  );
});

test("ports analytics snapshot totals and chart maxima", () => {
  assert.deepEqual(
    summarizeAnalyticsSnapshots([
      {
        plannedIncome: 6000,
        plannedFixedExpenses: 1500,
        plannedVariableExpenses: 700,
        expectedCashFlow: 3750,
        actualIncome: 6000,
        actualTotalExpenses: 1000,
        netCashFlow: 5000,
      },
      {
        plannedIncome: 6000,
        plannedFixedExpenses: 1500,
        plannedVariableExpenses: 700,
        expectedCashFlow: 3750,
        actualIncome: 0,
        actualTotalExpenses: 1000,
        netCashFlow: -1000,
      },
    ]),
    {
      totalIncome: 6000,
      totalSpending: 2000,
      totalExpectedCashFlow: 7500,
      totalNetCashFlow: 4000,
      averageIncome: 3000,
      averageSpending: 1000,
      averageNetCashFlow: 2000,
      maxIncome: 6000,
      maxSpending: 2200,
      maxCashFlow: 5000,
    },
  );
});

test("ports Flask amortization and linked debt progress", () => {
  const summary = amortizationSummary(1200, 0, 500, 100, 12);
  assert.deepEqual(summary, { months: 6, years: 0.5, interestPaid: 0, payoffPossible: true });

  const debtGoal = {
    goalType: "debt",
    targetAmount: 1200,
    currentAmount: 500,
    monthlyContribution: 25,
    targetDate: "2027-01-14",
  };
  const extra = requiredExtraPaymentForDebtGoal(
    debtGoal,
    { principalBalance: 1200, annualInterestRate: 0, regularPayment: 500, termMonths: 12 },
    "2026-07-14",
  );
  assert.ok(Math.abs(extra - 100) <= 0.01);
  assert.deepEqual(calculateGoalProgress(debtGoal, 1200), {
    progress: 0,
    remaining: 1200,
    currentAmount: 0,
    targetAmount: 1200,
  });
});

test("ports Flask loan scenarios and full amortization schedule", () => {
  const scenarios = loanPlanScenarios({
    principalBalance: 1200,
    annualInterestRate: 0,
    regularPayment: 500,
    termMonths: 12,
    extraPaymentOne: 100,
    extraPaymentTwo: 200,
  });
  assert.deepEqual(scenarios.map(({ key, months }) => ({ key, months })), [
    { key: "base", months: 12 },
    { key: "extra_one", months: 6 },
    { key: "extra_two", months: 4 },
  ]);

  const schedule = amortizationSchedule(1200, 0, 500, 100, 12, "2026-07-01");
  assert.equal(schedule.length, 6);
  assert.deepEqual(schedule[0], {
    month: 1,
    paymentDate: "2026-07-01",
    beginningBalance: 1200,
    payment: 200,
    principal: 200,
    interest: 0,
    endingBalance: 1000,
  });
  assert.deepEqual(schedule.at(-1), {
    month: 6,
    paymentDate: "2026-12-01",
    beginningBalance: 200,
    payment: 200,
    principal: 200,
    interest: 0,
    endingBalance: 0,
  });
});
