import type { components } from "@clearpath/api-client";
import { plannerGuidanceSchema, plannerPageContextResponseSchema, plannerViewSchema } from "@clearpath/validation";

type ApiGuidance = components["schemas"]["PlannerGuidanceResponse"];
type ApiContext = components["schemas"]["PlannerPageContextResponse"];
type ApiMe = components["schemas"]["MeResponse"];
type ApiGuidanceItem = components["schemas"]["PlannerGuidanceItemResponse"];

function mapItem(row: ApiGuidanceItem) {
  return {
    title: row.title,
    body: row.body,
    level: row.level,
    type: row.type,
    disclaimer: row.disclaimer ?? null,
    action: row.action ? { label: row.action.label, target: row.action.target } : null,
  };
}

export function mapPlannerGuidance(data: ApiGuidance) {
  return plannerGuidanceSchema.safeParse({
    source: data.source,
    provider: data.provider,
    model: data.model,
    items: (data.items ?? []).map(mapItem),
    status: data.status,
    message: data.message,
    generatedAt: data.generated_at ?? null,
    modelOptions: (data.model_options ?? []).map((provider) => ({
      key: provider.key,
      label: provider.label,
      configured: provider.configured,
      models: (provider.models ?? []).map((model) => ({ id: model.id, label: model.label })),
    })),
    selectedProvider: data.selected_provider,
    selectedModel: data.selected_model,
    usage: {
      burstCount: data.usage.burst_count,
      dailyCount: data.usage.daily_count,
      monthlyCount: data.usage.monthly_count,
      monthlyCostCents: data.usage.monthly_cost_cents,
      burstLimit: data.usage.burst_limit,
      dailyLimit: data.usage.daily_limit,
      monthlyLimit: data.usage.monthly_limit,
      monthlyCostLimitCents: data.usage.monthly_cost_limit_cents,
      currentLimitReason: data.usage.current_limit_reason ?? null,
    },
  });
}

export function mapPlannerView(guidance: ApiGuidance, me: ApiMe) {
  const mappedGuidance = mapPlannerGuidance(guidance);
  if (!mappedGuidance.success) return mappedGuidance;
  return plannerViewSchema.safeParse({
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
    guidance: mappedGuidance.data,
  });
}

export function mapPlannerPageContext(data: ApiContext) {
  return plannerPageContextResponseSchema.safeParse({
    source: data.source,
    provider: data.provider,
    model: data.model,
    items: (data.items ?? []).map(mapItem),
    status: data.status,
    message: data.message,
  });
}
