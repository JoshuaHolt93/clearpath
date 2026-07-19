import type { components } from "@clearpath/api-client";
import { loanPlanDetailSchema, loanPlanDirectorySchema, loanPlanResourceSchema } from "@clearpath/validation";

type ApiList = components["schemas"]["LoanPlanListResponse"];
type ApiResource = components["schemas"]["LoanPlanResponse"];
type ApiMe = components["schemas"]["MeResponse"];

function mapSession(me: ApiMe) {
  return {
    ownerUserId: me.id,
    householdName: me.household_name ?? null,
    selectedPlan: me.selected_plan,
    billingStatus: me.billing_status,
    planDisplayName: me.plan_display_name,
    primaryAccountHolder: me.primary_account_holder,
    subject: {
      id: me.session_subject.id,
      subjectType: me.session_subject.subject_type,
      email: me.session_subject.email,
      displayName: me.session_subject.display_name,
      firstName: me.session_subject.first_name,
      avatarInitial: me.session_subject.avatar_initial,
      householdRole: me.session_subject.household_role ?? null,
    },
    featureAccess: (me.feature_access ?? []).map((row) => ({ feature: row.feature, enabled: row.enabled, hidden: row.hidden, requiredPlan: row.required_plan })),
  };
}

export function mapLoanDirectory(data: ApiList, me: ApiMe) {
  return loanPlanDirectorySchema.safeParse({
    session: mapSession(me),
    items: (data.items ?? []).map((row) => ({
      fixedExpenseItemId: row.fixed_expense_item_id,
      name: row.name,
      loanKind: row.loan_kind,
      monthlyPayment: row.monthly_payment,
      selectedExtra: row.selected_extra,
      totalMonthly: row.total_monthly,
      principalBalance: row.principal_balance,
      currentBalance: row.current_balance,
      collateralValue: row.collateral_value,
      selectedScenario: row.selected_scenario,
    })),
    totalDebtMonthly: data.total_debt_monthly,
    totalDebtBalance: data.total_debt_balance,
    debtToIncomeRatio: data.debt_to_income_ratio,
    loanCategoryLabelOptions: data.loan_category_label_options ?? [],
    today: data.today,
    recurringFrequencyOptions: data.recurring_frequency_options ?? {},
    weekdayOptions: data.weekday_options ?? {},
    monthlyWeekOptions: data.monthly_week_options ?? {},
  });
}

export function mapLoanResource(data: ApiResource) {
  return loanPlanResourceSchema.safeParse({
    fixedExpense: {
      id: data.fixed_expense.id,
      name: data.fixed_expense.name,
      amount: data.fixed_expense.amount,
      frequency: data.fixed_expense.frequency,
      startDate: data.fixed_expense.start_date,
      categoryLabel: data.fixed_expense.category_label ?? null,
      isLoan: data.fixed_expense.is_loan,
      monthlyAmount: data.fixed_expense.monthly_amount ?? null,
    },
    loanKind: data.loan_kind,
    plan: data.plan ? {
      id: data.plan.id,
      fixedExpenseItemId: data.plan.fixed_expense_item_id,
      loanType: data.plan.loan_type,
      principalBalance: data.plan.principal_balance,
      collateralValue: data.plan.collateral_value,
      annualInterestRate: data.plan.annual_interest_rate,
      termMonths: data.plan.term_months,
      termUnitPreference: data.plan.term_unit_preference,
      regularPayment: data.plan.regular_payment,
      extraPaymentOne: data.plan.extra_payment_one,
      extraPaymentTwo: data.plan.extra_payment_two,
      selectedScenario: data.plan.selected_scenario,
      notes: data.plan.notes ?? null,
    } : null,
    scenarios: (data.scenarios ?? []).map((row) => ({ key: row.key, label: row.label, extraPayment: row.extra_payment, months: row.months, years: row.years, interestPaid: row.interest_paid, payoffPossible: row.payoff_possible })),
    selectedSchedule: (data.selected_schedule ?? []).map((row) => ({ month: row.month, paymentDate: row.payment_date, beginningBalance: row.beginning_balance, payment: row.payment, principal: row.principal, interest: row.interest, endingBalance: row.ending_balance })),
    createdFixedExpense: data.created_fixed_expense,
  });
}

export function mapLoanDetail(data: ApiResource, me: ApiMe) {
  const resource = mapLoanResource(data);
  if (!resource.success) return resource;
  return loanPlanDetailSchema.safeParse({ session: mapSession(me), resource: resource.data });
}
