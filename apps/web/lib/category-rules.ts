import type { components } from "@clearpath/api-client";
import { categoryRulesViewSchema } from "@clearpath/validation";

type ApiMe = components["schemas"]["MeResponse"];
type ApiRuleList = components["schemas"]["CategoryRuleListResponse"];
type ApiCategory = components["schemas"]["CategoryResponse"];

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

function mapCategory(row: ApiCategory) {
  return {
    id: row.id,
    name: row.name,
    kind: row.kind,
    monthlyTarget: row.monthly_target,
    isDefault: row.is_default,
    canManage: row.can_manage ?? false,
  };
}

function text(row: Record<string, unknown>, key: string, fallback = "") {
  const value = row[key];
  return typeof value === "string" ? value : fallback;
}

export function mapCategoryRules(data: ApiRuleList, me: ApiMe) {
  const categories = data.categories.map(mapCategory);
  const categoryById = new Map(categories.map((category) => [category.id, category]));
  return categoryRulesViewSchema.safeParse({
    session: mapSession(me),
    categories,
    rules: data.rules.map((rule) => ({
      id: rule.id,
      category: categoryById.get(rule.category.id) ?? mapCategory(rule.category),
      matchText: rule.match_text,
      matchType: rule.match_type,
      ruleLogic: rule.rule_logic,
      conditions: rule.conditions.map((condition, index) => ({
        field: text(condition, "field", "description"),
        operator: text(condition, "operator", "contains"),
        value: text(condition, "value", rule.match_text),
        valueSecondary: text(condition, "value_secondary"),
        group: text(condition, "group", "primary"),
        join: index === 0 ? "and" : text(condition, "join", "and"),
      })),
      summary: rule.summary,
      createdAt: rule.created_at,
      updatedAt: rule.updated_at,
      appliedCount: rule.applied_count ?? null,
    })),
  });
}
