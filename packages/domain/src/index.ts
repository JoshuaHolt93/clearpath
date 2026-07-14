export interface GoalMathInput {
  goalType: string;
  targetAmount: number;
  currentAmount: number;
  monthlyContribution: number;
  targetDate?: string | null;
}

export interface LoanMathInput {
  principalBalance: number;
  annualInterestRate: number;
  regularPayment: number;
  termMonths: number;
}

export interface AmortizationSummary {
  months: number;
  years: number;
  interestPaid: number;
  payoffPossible: boolean;
}

export interface GoalProgress {
  progress: number;
  remaining: number;
  currentAmount: number;
  targetAmount: number;
}

interface CalendarDateParts {
  year: number;
  month: number;
  day: number;
}

function calendarDateParts(value: string): CalendarDateParts {
  const [year, month, day] = value.split("-").map(Number);
  return { year, month, day };
}

function roundHalfEven(value: number): number {
  const lower = Math.floor(value);
  const fraction = value - lower;
  if (Math.abs(fraction - 0.5) <= Number.EPSILON * Math.max(Math.abs(value), 1)) {
    return lower % 2 === 0 ? lower : lower + 1;
  }
  return Math.round(value);
}

export function monthsUntil(targetDate: string | null | undefined, startDate: string): number {
  if (!targetDate) return 0;
  const target = calendarDateParts(targetDate);
  const start = calendarDateParts(startDate);
  const targetOrdinal = target.year * 372 + target.month * 31 + target.day;
  const startOrdinal = start.year * 372 + start.month * 31 + start.day;
  if (targetOrdinal <= startOrdinal) return 0;

  let months = (target.year - start.year) * 12 + (target.month - start.month);
  if (target.day > start.day) months += 1;
  return Math.max(months, 1);
}

export function requiredMonthlyForGoal(goal: GoalMathInput, startDate: string): number {
  const remaining = Math.max(goal.targetAmount - goal.currentAmount, 0);
  const months = monthsUntil(goal.targetDate, startDate);
  if (remaining <= 0 || months <= 0) return 0;
  return remaining / months;
}

export function estimateGoalTimeline(goal: GoalMathInput, startDate: string): string {
  const remaining = Math.max(goal.targetAmount - goal.currentAmount, 0);
  if (remaining <= 0) return "Complete";
  if (goal.monthlyContribution <= 0) {
    if (goal.targetDate) {
      const required = requiredMonthlyForGoal(goal, startDate);
      const formatted = roundHalfEven(required).toLocaleString("en-US");
      if (goal.goalType === "savings") return `Save $${formatted}/month to hit target date`;
      return `Pay $${formatted}/month extra to hit target date`;
    }
    return "No contribution pace yet";
  }
  const months = Math.floor((remaining + goal.monthlyContribution - 1) / goal.monthlyContribution);
  return `About ${months} month${months !== 1 ? "s" : ""}`;
}

export function savingsGoalBudgetLabel(goalName: string): string {
  const normalized = goalName.trim().toLowerCase().split(/\s+/).filter(Boolean).join(" ");
  if (normalized.includes("education") || normalized.includes("college") || normalized.includes("tuition")) {
    return "Education Savings";
  }
  if (normalized.includes("retirement") || normalized.includes("401k") || normalized.includes("ira")) {
    return "Retirement (401k, IRA)";
  }
  if (normalized.includes("invest") || normalized.includes("brokerage")) return "Investments";
  return "Emergency Fund";
}

export function scheduledPaymentForTerm(principal: number, annualRate: number, termMonths: number): number {
  principal = Math.max(principal || 0, 0);
  termMonths = Math.max(Math.trunc(termMonths || 0), 1);
  const monthlyRate = Math.max(annualRate || 0, 0) / 100 / 12;
  if (principal <= 0) return 0;
  if (monthlyRate <= 0) return principal / termMonths;
  const factor = (1 + monthlyRate) ** termMonths;
  return principal * monthlyRate * factor / (factor - 1);
}

export function amortizationSummary(
  principal: number,
  annualRate: number,
  payment: number,
  extraPayment = 0,
  maxMonths = 360,
): AmortizationSummary {
  principal = Math.max(principal || 0, 0);
  const monthlyRate = Math.max(annualRate || 0, 0) / 100 / 12;
  const baselinePayment = maxMonths ? scheduledPaymentForTerm(principal, annualRate, maxMonths) : payment || 0;
  const monthlyPayment = Math.max(baselinePayment + (extraPayment || 0), 0);
  if (principal <= 0 || monthlyPayment <= 0) {
    return { months: 0, years: 0, interestPaid: 0, payoffPossible: principal <= 0 };
  }
  if (monthlyRate && monthlyPayment <= principal * monthlyRate) {
    return { months: maxMonths, years: maxMonths / 12, interestPaid: 0, payoffPossible: false };
  }

  let balance = principal;
  let interestPaid = 0;
  let months = 0;
  const limit = Math.max(maxMonths, 1) + 600;
  while (balance > 0.01 && months < limit) {
    const interest = balance * monthlyRate;
    const principalPaid = Math.min(monthlyPayment - interest, balance);
    if (principalPaid <= 0) {
      return { months, years: months / 12, interestPaid, payoffPossible: false };
    }
    interestPaid += interest;
    balance -= principalPaid;
    months += 1;
  }
  return { months, years: months / 12, interestPaid, payoffPossible: balance <= 0.01 };
}

export function requiredExtraPaymentForDebtGoal(
  goal: GoalMathInput,
  loan: LoanMathInput | null,
  startDate: string,
): number {
  if (goal.goalType !== "debt" || !goal.targetDate || !loan || loan.principalBalance <= 0) return 0;
  const targetMonths = monthsUntil(goal.targetDate, startDate);
  if (targetMonths <= 0) return 0;

  const baseline = amortizationSummary(
    loan.principalBalance,
    loan.annualInterestRate,
    loan.regularPayment,
    0,
    loan.termMonths,
  );
  if (baseline.payoffPossible && baseline.months <= targetMonths) return 0;

  let high = Math.max(loan.principalBalance / Math.max(targetMonths, 1), loan.regularPayment, 100);
  for (let index = 0; index < 20; index += 1) {
    const candidate = amortizationSummary(
      loan.principalBalance,
      loan.annualInterestRate,
      loan.regularPayment,
      high,
      loan.termMonths,
    );
    if (candidate.payoffPossible && candidate.months <= targetMonths) break;
    high *= 2;
  }

  let low = 0;
  for (let index = 0; index < 32; index += 1) {
    const midpoint = (low + high) / 2;
    const candidate = amortizationSummary(
      loan.principalBalance,
      loan.annualInterestRate,
      loan.regularPayment,
      midpoint,
      loan.termMonths,
    );
    if (candidate.payoffPossible && candidate.months <= targetMonths) high = midpoint;
    else low = midpoint;
  }
  return high;
}

export function calculateGoalProgress(goal: GoalMathInput, linkedPrincipalBalance?: number | null): GoalProgress {
  let targetAmount = goal.targetAmount || 0;
  let currentAmount = goal.currentAmount || 0;
  let remaining = Math.max(targetAmount - currentAmount, 0);
  if (goal.goalType === "debt" && linkedPrincipalBalance != null) {
    targetAmount = goal.targetAmount || linkedPrincipalBalance || 0;
    remaining = Math.max(linkedPrincipalBalance || 0, 0);
    currentAmount = Math.max(targetAmount - remaining, 0);
  }
  const progress = targetAmount <= 0 ? 0 : Math.min((currentAmount / targetAmount) * 100, 100);
  return { progress, remaining, currentAmount, targetAmount };
}
