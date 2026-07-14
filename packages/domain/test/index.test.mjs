import assert from "node:assert/strict";
import test from "node:test";

import {
  amortizationSummary,
  calculateGoalProgress,
  estimateGoalTimeline,
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
