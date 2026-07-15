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

export interface LoanPlanMathInput extends LoanMathInput {
  extraPaymentOne: number;
  extraPaymentTwo: number;
}

export interface RetirementMathInput {
  retirementEnabled: boolean;
  retirementHasEmployerPlan: boolean;
  retirementEmployerWithheld: boolean;
  retirementMonthlyContribution: number;
  retirementPersonalMonthlyContribution: number;
  incomeBasis: string | null | undefined;
}

export interface DashboardMetricMathInput {
  plannedIncome: number;
  monthlyTax: number;
  fixedExpenses: number;
  plannedSavings: number;
  plannedDebtPayment: number;
  retirementContribution: number;
  loanExtraPayment: number;
  variableSpend: number;
  recordedIncome: number;
  totalExpenses: number;
  safeToSpendTarget: number;
  dayOfMonth: number;
  daysInMonth: number;
}

export interface DashboardMetricMathResult {
  safeToSpend: number;
  netCashFlow: number;
  expectedVariableSpend: number;
  onTrackStatus: "green" | "yellow" | "red";
}

export interface NetWorthAccountMathInput {
  balance: number;
  isLiability: boolean;
}

export interface NetWorthLoanMathInput {
  principalBalance: number;
  collateralValue: number;
}

export interface NetWorthMathResult {
  assets: number;
  liabilities: number;
  loanBalances: number;
  collateralAssets: number;
  collateralValue: number;
  securedLoanEquity: number;
  securedNegativeEquity: number;
  securedLoanBalances: number;
  unsecuredLoanBalances: number;
  debtGoals: number;
  netWorth: number;
}

export interface AnalyticsSnapshotMathInput {
  plannedIncome: number;
  plannedFixedExpenses: number;
  plannedVariableExpenses: number;
  expectedCashFlow: number;
  actualIncome: number;
  actualTotalExpenses: number;
  netCashFlow: number;
}

export interface AnalyticsSnapshotMathSummary {
  totalIncome: number;
  totalSpending: number;
  totalExpectedCashFlow: number;
  totalNetCashFlow: number;
  averageIncome: number;
  averageSpending: number;
  averageNetCashFlow: number;
  maxIncome: number;
  maxSpending: number;
  maxCashFlow: number;
}

export interface AmortizationSummary {
  months: number;
  years: number;
  interestPaid: number;
  payoffPossible: boolean;
}

export interface AmortizationScheduleRow {
  month: number;
  paymentDate: string;
  beginningBalance: number;
  payment: number;
  principal: number;
  interest: number;
  endingBalance: number;
}

export interface LoanPlanScenario extends AmortizationSummary {
  key: "base" | "extra_one" | "extra_two";
  label: string;
  extraPayment: number;
}

export interface GoalProgress {
  progress: number;
  remaining: number;
  currentAmount: number;
  targetAmount: number;
}

export function retirementCashFlowContribution(profile: RetirementMathInput | null | undefined): number {
  if (!profile || !profile.retirementEnabled) return 0;
  let employerContribution = Math.max(profile.retirementMonthlyContribution || 0, 0);
  const personalContribution = Math.max(profile.retirementPersonalMonthlyContribution || 0, 0);
  if (profile.retirementEmployerWithheld && (profile.incomeBasis || "take_home") !== "gross") {
    employerContribution = 0;
  }
  return employerContribution + personalContribution;
}

export function retirementTaxableIncomeAdjustment(profile: RetirementMathInput | null | undefined): number {
  if (!profile || !profile.retirementEnabled || !profile.retirementHasEmployerPlan) return 0;
  if (!profile.retirementEmployerWithheld) return 0;
  return Math.max(profile.retirementMonthlyContribution || 0, 0) * 12;
}

export function calculateDashboardMetricValues(input: DashboardMetricMathInput): DashboardMetricMathResult {
  const safeToSpend =
    input.plannedIncome
    - input.monthlyTax
    - input.fixedExpenses
    - input.plannedSavings
    - input.plannedDebtPayment
    - input.retirementContribution
    - input.loanExtraPayment
    - input.variableSpend;
  const netCashFlow = input.recordedIncome - input.totalExpenses;
  const dayOfMonth = Math.max(input.dayOfMonth, 1);
  const daysInMonth = Math.max(input.daysInMonth, 1);
  const expectedVariableSpend = Math.max(input.safeToSpendTarget, 0) * (dayOfMonth / daysInMonth);
  let onTrackStatus: DashboardMetricMathResult["onTrackStatus"] = "red";
  if (input.variableSpend <= expectedVariableSpend * 1.05) onTrackStatus = "green";
  else if (input.variableSpend <= expectedVariableSpend * 1.2) onTrackStatus = "yellow";
  return { safeToSpend, netCashFlow, expectedVariableSpend, onTrackStatus };
}

export function calculateNetWorthSummary(
  accounts: NetWorthAccountMathInput[],
  loans: NetWorthLoanMathInput[],
  unlinkedDebtGoalBalances: number[],
): NetWorthMathResult {
  let accountAssets = 0;
  let accountLiabilities = 0;
  for (const account of accounts) {
    const balance = account.balance || 0;
    if (account.isLiability || balance < 0) accountLiabilities += Math.abs(balance);
    else accountAssets += balance;
  }

  let loanBalances = 0;
  let collateralValue = 0;
  let securedPositiveEquity = 0;
  let securedNegativeEquity = 0;
  let securedLoanBalances = 0;
  let unsecuredLoanBalances = 0;
  for (const loan of loans) {
    const balance = Math.max(loan.principalBalance || 0, 0);
    const collateral = Math.max(loan.collateralValue || 0, 0);
    loanBalances += balance;
    collateralValue += collateral;
    if (collateral) {
      securedLoanBalances += balance;
      const equity = collateral - balance;
      if (equity >= 0) securedPositiveEquity += equity;
      else securedNegativeEquity += Math.abs(equity);
    } else {
      unsecuredLoanBalances += balance;
    }
  }

  accountAssets += securedPositiveEquity;
  const debtGoals = unlinkedDebtGoalBalances.reduce((total, balance) => total + Math.max(balance || 0, 0), 0);
  const liabilities = accountLiabilities + loanBalances + debtGoals;
  return {
    assets: accountAssets,
    liabilities,
    loanBalances,
    collateralAssets: securedPositiveEquity,
    collateralValue,
    securedLoanEquity: securedPositiveEquity - securedNegativeEquity,
    securedNegativeEquity,
    securedLoanBalances,
    unsecuredLoanBalances,
    debtGoals,
    netWorth: accountAssets - liabilities,
  };
}

export function summarizeAnalyticsSnapshots(snapshots: AnalyticsSnapshotMathInput[]): AnalyticsSnapshotMathSummary {
  const count = snapshots.length;
  const totalIncome = snapshots.reduce((total, snapshot) => total + snapshot.actualIncome, 0);
  const totalSpending = snapshots.reduce((total, snapshot) => total + snapshot.actualTotalExpenses, 0);
  const totalExpectedCashFlow = snapshots.reduce((total, snapshot) => total + snapshot.expectedCashFlow, 0);
  const totalNetCashFlow = snapshots.reduce((total, snapshot) => total + snapshot.netCashFlow, 0);
  return {
    totalIncome,
    totalSpending,
    totalExpectedCashFlow,
    totalNetCashFlow,
    averageIncome: count ? totalIncome / count : 0,
    averageSpending: count ? totalSpending / count : 0,
    averageNetCashFlow: count ? totalNetCashFlow / count : 0,
    maxIncome: Math.max(1, ...snapshots.flatMap((snapshot) => [snapshot.actualIncome, snapshot.plannedIncome])),
    maxSpending: Math.max(
      1,
      ...snapshots.flatMap((snapshot) => [
        snapshot.actualTotalExpenses,
        snapshot.plannedFixedExpenses + snapshot.plannedVariableExpenses,
      ]),
    ),
    maxCashFlow: Math.max(
      1,
      ...snapshots.flatMap((snapshot) => [Math.abs(snapshot.netCashFlow), Math.abs(snapshot.expectedCashFlow)]),
    ),
  };
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

function addCalendarMonths(value: string, months: number): string {
  const start = calendarDateParts(value);
  const monthIndex = start.month - 1 + months;
  const year = start.year + Math.floor(monthIndex / 12);
  const month = ((monthIndex % 12) + 12) % 12 + 1;
  const lastDay = new Date(Date.UTC(year, month, 0)).getUTCDate();
  const day = Math.min(start.day, lastDay);
  return `${year.toString().padStart(4, "0")}-${month.toString().padStart(2, "0")}-${day.toString().padStart(2, "0")}`;
}

export function amortizationSchedule(
  principal: number,
  annualRate: number,
  payment: number,
  extraPayment = 0,
  maxMonths = 360,
  startMonth: string,
): AmortizationScheduleRow[] {
  principal = Math.max(principal || 0, 0);
  const monthlyRate = Math.max(annualRate || 0, 0) / 100 / 12;
  // Flask derives the baseline from the term whenever maxMonths is present.
  const baselinePayment = maxMonths ? scheduledPaymentForTerm(principal, annualRate, maxMonths) : payment || 0;
  const monthlyPayment = Math.max(baselinePayment + (extraPayment || 0), 0);
  if (principal <= 0 || monthlyPayment <= 0) return [];

  let balance = principal;
  const rows: AmortizationScheduleRow[] = [];
  const limit = Math.max(maxMonths, 1) + 600;
  for (let monthNumber = 1; monthNumber <= limit; monthNumber += 1) {
    const interest = balance * monthlyRate;
    const principalPaid = Math.min(monthlyPayment - interest, balance);
    if (principalPaid <= 0) break;
    const endingBalance = Math.max(balance - principalPaid, 0);
    rows.push({
      month: monthNumber,
      paymentDate: addCalendarMonths(startMonth, monthNumber - 1),
      beginningBalance: balance,
      payment: principalPaid + interest,
      principal: principalPaid,
      interest,
      endingBalance,
    });
    balance = endingBalance;
    if (balance <= 0.01) break;
  }
  return rows;
}

export function loanPlanScenarios(plan: LoanPlanMathInput): LoanPlanScenario[] {
  const scenarios = [
    ["base", "Current Payment", 0],
    ["extra_one", "Extra Payment Scenario 1", plan.extraPaymentOne || 0],
    ["extra_two", "Extra Payment Scenario 2", plan.extraPaymentTwo || 0],
  ] as const;
  return scenarios.map(([key, label, extraPayment]) => ({
    key,
    label,
    extraPayment,
    ...amortizationSummary(
      plan.principalBalance,
      plan.annualInterestRate,
      plan.regularPayment,
      extraPayment,
      plan.termMonths || 360,
    ),
  }));
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
