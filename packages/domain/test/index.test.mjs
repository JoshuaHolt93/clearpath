import assert from "node:assert/strict";
import test from "node:test";

import {
  amortizationSchedule,
  amortizationSummary,
  calculateGoalProgress,
  estimateGoalTimeline,
  loanPlanScenarios,
  monthsUntil,
  requiredExtraPaymentForDebtGoal,
  requiredMonthlyForGoal,
  savingsGoalBudgetLabel,
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
