import type { components } from "@clearpath/api-client";
import { analyticsViewSchema } from "@clearpath/validation";

type ApiAnalytics = components["schemas"]["AnalyticsResponse"];
type ApiMe = components["schemas"]["MeResponse"];
type ApiSummary = components["schemas"]["AnalyticsSummaryResponse"];
type ApiSubscription = components["schemas"]["AnalyticsSubscriptionResponse"];

function mapSubscription(row: ApiSubscription) {
  return {
    id: row.id,
    name: row.name,
    serviceCategory: row.service_category,
    monthlyAmount: row.monthly_amount,
    annualAmount: row.annual_amount,
    cycle: row.cycle,
    confidence: row.confidence,
    status: row.status,
    replaceable: row.replaceable,
    nextChargeDate: row.next_charge_date ?? null,
  };
}

function mapSummary(summary: ApiSummary) {
  return {
    rangeKey: summary.range_key,
    rangeLabel: summary.range_label,
    months: summary.months,
    snapshots: summary.snapshots.map((row) => ({
      month: row.month,
      plannedIncome: row.planned_income,
      plannedFixedExpenses: row.planned_fixed_expenses,
      plannedVariableExpenses: row.planned_variable_expenses,
      plannedSavings: row.planned_savings,
      plannedDebtPayment: row.planned_debt_payment,
      plannedTaxes: row.planned_taxes,
      plannedRetirement: row.planned_retirement,
      plannedSafeToSpend: row.planned_safe_to_spend,
      expectedCashFlow: row.expected_cash_flow,
      budgetRemaining: row.budget_remaining,
      actualIncome: row.actual_income,
      actualFixedExpenses: row.actual_fixed_expenses,
      actualVariableExpenses: row.actual_variable_expenses,
      actualTotalExpenses: row.actual_total_expenses,
      netCashFlow: row.net_cash_flow,
    })),
    startDate: summary.start_date,
    endDate: summary.end_date,
    totalIncome: summary.total_income,
    totalSpending: summary.total_spending,
    totalExpectedCashFlow: summary.total_expected_cash_flow,
    totalNetCashFlow: summary.total_net_cash_flow,
    averageIncome: summary.average_income,
    averageSpending: summary.average_spending,
    averageNetCashFlow: summary.average_net_cash_flow,
    maxIncome: summary.max_income,
    maxSpending: summary.max_spending,
    maxCashFlow: summary.max_cash_flow,
    categoryRows: summary.category_rows.map((row) => ({ category: row.category, categoryId: row.category_id ?? null, amount: row.amount })),
    subscriptions: {
      subscriptions: (summary.subscriptions.subscriptions ?? []).map(mapSubscription),
      activeCount: summary.subscriptions.active_count,
      reviewCount: summary.subscriptions.review_count,
      actionCount: summary.subscriptions.action_count,
      manageLinkCount: summary.subscriptions.manage_link_count,
      monthlyTotal: summary.subscriptions.monthly_total,
      annualTotal: summary.subscriptions.annual_total,
      potentialSavings: summary.subscriptions.potential_savings,
      spendingShare: summary.subscriptions.spending_share,
      categoryBreakdown: (summary.subscriptions.category_breakdown ?? []).map((row) => ({ category: row.category, amount: row.amount, percent: row.percent })),
      opportunities: (summary.subscriptions.opportunities ?? []).map((row) => ({ subscription: mapSubscription(row.subscription), reason: row.reason })),
      upcoming: (summary.subscriptions.upcoming ?? []).map(mapSubscription),
    },
  };
}

export function mapAnalytics(data: ApiAnalytics, me: ApiMe) {
  return analyticsViewSchema.safeParse({
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
      featureAccess: (me.feature_access ?? []).map((row) => ({
        feature: row.feature,
        enabled: row.enabled,
        hidden: row.hidden,
        requiredPlan: row.required_plan,
      })),
    },
    summary: mapSummary(data.summary),
    budgetHistorySummary: mapSummary(data.budget_history_summary),
    debtToIncomeRatio: data.debt_to_income_ratio,
    rangeOptions: data.range_options,
    selectedRange: data.selected_range,
    endMonth: data.end_month,
    selectedHistoryRange: data.selected_history_range,
    historyEndMonth: data.history_end_month,
    subscriptionAnalyticsEnabled: data.subscription_analytics_enabled,
    subscriptionAnalyticsPlanLabel: data.subscription_analytics_plan_label,
    aiCoachEnabled: data.ai_coach_enabled,
    aiCoachHidden: data.ai_coach_hidden,
  });
}
