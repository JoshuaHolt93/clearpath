import type { components } from "@clearpath/api-client";
import { subscriptionsViewSchema } from "@clearpath/validation";

type ApiMe = components["schemas"]["MeResponse"];
type ApiSubscriptions = components["schemas"]["SubscriptionListResponse"];

function mapSession(data: ApiMe) {
  return {
    ownerUserId: data.id,
    householdName: data.household_name ?? null,
    selectedPlan: data.selected_plan,
    billingStatus: data.billing_status,
    planDisplayName: data.plan_display_name,
    primaryAccountHolder: data.primary_account_holder,
    subject: {
      id: data.session_subject.id,
      subjectType: data.session_subject.subject_type,
      email: data.session_subject.email,
      displayName: data.session_subject.display_name,
      firstName: data.session_subject.first_name,
      avatarInitial: data.session_subject.avatar_initial,
      householdRole: data.session_subject.household_role ?? null,
    },
    featureAccess: (data.feature_access ?? []).map((row) => ({
      feature: row.feature,
      enabled: row.enabled,
      hidden: row.hidden,
      requiredPlan: row.required_plan,
    })),
  };
}

export function mapSubscriptions(data: ApiSubscriptions, me: ApiMe) {
  return subscriptionsViewSchema.safeParse({
    session: mapSession(me),
    subscriptions: data.subscriptions.map((row) => ({
      id: row.id,
      merchantKey: row.merchant_key,
      name: row.name,
      category: row.category,
      serviceCategory: row.service_category,
      amount: row.amount,
      monthlyAmount: row.monthly_amount,
      annualAmount: row.annual_amount,
      cycle: row.cycle,
      cycleDays: row.cycle_days,
      confidence: row.confidence,
      status: row.status,
      cancelUrl: row.cancel_url ?? null,
      replaceable: row.replaceable,
      firstSeen: row.first_seen ?? null,
      lastSeen: row.last_seen ?? null,
      nextChargeDate: row.next_charge_date ?? null,
      notes: row.notes ?? null,
      isManual: row.is_manual,
      cycleIsManual: row.cycle_is_manual,
      evidence: (row.evidence ?? []).map((item) => ({
        id: item.id ?? null,
        date: item.date ?? null,
        description: item.description ?? null,
        amount: item.amount ?? null,
      })),
    })),
    summary: {
      activeCount: data.summary.active_count,
      reviewCount: data.summary.review_count,
      actionCount: data.summary.action_count,
      manageLinkCount: data.summary.manage_link_count,
      monthlyTotal: data.summary.monthly_total,
      annualTotal: data.summary.annual_total,
      potentialSavings: data.summary.potential_savings,
      averageConfidence: data.summary.average_confidence,
      transactionCount: data.summary.transaction_count,
    },
    categoryBreakdown: data.category_breakdown.map((row) => ({ category: row.category, amount: row.amount, percent: row.percent })),
    opportunities: data.opportunities.map((row) => ({ subscriptionId: row.subscription_id, reason: row.reason })),
    upcomingSubscriptionIds: data.upcoming_subscription_ids,
    statuses: data.statuses,
    cycles: data.cycles,
  });
}
