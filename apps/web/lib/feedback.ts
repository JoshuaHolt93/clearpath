import type { components } from "@clearpath/api-client";
import { complianceViewSchema, feedbackViewSchema } from "@clearpath/validation";

type ApiMe = components["schemas"]["MeResponse"];
type ApiFeedbackOptions = { reasons: string[][]; feature_expectation_reasons: string[][]; broken_features: string[][] };
type ApiEvaluations = components["schemas"]["ControlEvaluationListResponse"];

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

export function mapFeedback(me: ApiMe, options: ApiFeedbackOptions) {
  return feedbackViewSchema.safeParse({
    session: mapSession(me),
    options: {
      reasons: options.reasons,
      featureExpectationReasons: options.feature_expectation_reasons,
      brokenFeatures: options.broken_features,
    },
  });
}

export function mapCompliance(me: ApiMe, evaluations: ApiEvaluations | null) {
  return complianceViewSchema.safeParse({
    session: mapSession(me),
    isAdmin: me.is_admin,
    evaluations: (evaluations?.evaluations ?? []).map((row) => ({
      id: row.id,
      controlId: row.control_id,
      controlName: row.control_name,
      status: row.status,
      evidence: row.evidence,
      evaluatedAt: row.evaluated_at,
    })),
    controls: (evaluations?.controls ?? []).map((control) => ({
      id: String((control as Record<string, unknown>).id ?? ""),
      name: String((control as Record<string, unknown>).name ?? ""),
      description: String((control as Record<string, unknown>).description ?? ""),
      ownerRole: ((control as Record<string, unknown>).owner_role as string | undefined) ?? null,
      reviewCadence: ((control as Record<string, unknown>).review_cadence as string | undefined) ?? null,
    })),
  });
}
