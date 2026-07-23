import type { components } from "@clearpath/api-client";
import { settingsViewSchema } from "@clearpath/validation";

// openapi-typescript renders the Pydantic tuple fields as both `[string,
// string][]` and `string[][]` depending on the call site; widen those fields
// and let the Zod contract enforce the pair shape at runtime.
type ApiSettings = Omit<
  components["schemas"]["SettingsDashboardResponse"],
  "account_classification_options" | "feedback_options"
> & {
  account_classification_options?: string[][];
  feedback_options: Record<string, unknown>;
};
type ApiMe = components["schemas"]["MeResponse"];
type ApiMember = components["schemas"]["HouseholdMemberResponse"];
type ApiInvite = components["schemas"]["HouseholdInviteResponse"];

export function mapMember(row: ApiMember) {
  return {
    id: row.id,
    email: row.email,
    displayName: row.display_name ?? null,
    role: row.role ?? null,
    status: row.status,
    acceptedAt: row.accepted_at ?? null,
  };
}

export function mapInvite(row: ApiInvite) {
  return {
    id: row.id,
    email: row.email,
    role: row.role,
    status: row.status,
    expiresAt: row.expires_at ?? null,
  };
}

type FeedbackOptions = {
  reasons: [string, string][];
  feature_expectation_reasons: [string, string][];
  broken_features: [string, string][];
};

export function mapSettings(data: ApiSettings, me: ApiMe) {
  const feedbackOptions = data.feedback_options as unknown as FeedbackOptions;
  return settingsViewSchema.safeParse({
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
    email: data.email,
    displayName: data.display_name ?? null,
    householdName: data.household_name ?? null,
    rulesCount: data.rules_count,
    categoryRows: (data.category_rows ?? []).map((row) => ({
      id: row.category.id,
      name: row.category.name,
      kind: row.category.kind,
      monthlyTarget: row.category.monthly_target,
      canManage: row.can_manage,
      usage: row.usage,
    })),
    plaidStatus: data.plaid_status,
    pushMfa: data.push_mfa,
    mfaEnabled: data.mfa_enabled,
    mfaPreferredMethod: data.mfa_preferred_method,
    mfaPushEnabled: data.mfa_push_enabled,
    billingStatus: data.billing_status,
    feedbackOptions: {
      reasons: feedbackOptions.reasons,
      featureExpectationReasons: feedbackOptions.feature_expectation_reasons,
      brokenFeatures: feedbackOptions.broken_features,
    },
    householdRoleOptions: data.household_role_options,
    householdMembers: (data.household_members ?? []).map(mapMember),
    pendingHouseholdInvites: (data.pending_household_invites ?? []).map(mapInvite),
    canManageHouseholdAccess: data.can_manage_household_access,
    householdAccessIsShared: data.household_access_is_shared,
    ethicsAcknowledgedAt: data.ethics_acknowledged_at ?? null,
    ethicsPolicyVersion: data.ethics_policy_version ?? null,
    accountDeleteConfirmation: data.account_delete_confirmation,
    accountDeleteBillingBlocked: data.account_delete_billing_blocked,
  });
}
