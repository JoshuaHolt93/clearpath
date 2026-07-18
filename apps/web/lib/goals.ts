import type { components } from "@clearpath/api-client";
import { goalsViewSchema } from "@clearpath/validation";

type ApiGoal = components["schemas"]["GoalResponse"];
type ApiGoalList = components["schemas"]["GoalListResponse"];
type ApiMe = components["schemas"]["MeResponse"];

export function mapGoal(row: ApiGoal) {
  return {
    id: row.goal.id,
    name: row.goal.name,
    goalType: row.goal.goal_type === "debt" ? "debt" as const : "savings" as const,
    targetAmount: row.target_amount,
    currentAmount: row.current_amount,
    monthlyContribution: row.goal.monthly_contribution,
    targetDate: row.goal.target_date ?? null,
    fixedExpenseItemId: row.goal.fixed_expense_item_id ?? null,
    progress: row.progress,
    timeline: row.timeline,
    remaining: row.remaining,
    requiredMonthly: row.required_monthly,
    requiredExtra: row.required_extra,
    linkedItem: row.linked_item ? { id: row.linked_item.id, name: row.linked_item.name } : null,
  };
}

export function mapGoals(data: ApiGoalList, me: ApiMe) {
  return goalsViewSchema.safeParse({
    session: {
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
    },
    goals: (data.goals ?? []).map(mapGoal),
    loanOptions: (data.loan_options ?? []).map((row) => ({
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
  });
}
