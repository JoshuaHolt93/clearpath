import type { components } from "@clearpath/api-client";
import { retirementViewSchema } from "@clearpath/validation";

type ApiRetirement = components["schemas"]["RetirementPlanResponse"];
type ApiMe = components["schemas"]["MeResponse"];
type ApiProfile = components["schemas"]["RetirementProfileResponse"];

export function mapRetirementProfile(profile: ApiProfile) {
  return {
    retirementEnabled: profile.retirement_enabled,
    retirementHasEmployerPlan: profile.retirement_has_employer_plan,
    retirementEmployerWithheld: profile.retirement_employer_withheld,
    retirementHasPersonalPlan: profile.retirement_has_personal_plan,
    retirementMonthlyContribution: profile.retirement_monthly_contribution,
    retirementPersonalMonthlyContribution: profile.retirement_personal_monthly_contribution,
    retirementLifestyleNotes: profile.retirement_lifestyle_notes ?? null,
    retirementLocationNotes: profile.retirement_location_notes ?? null,
    retirementHealthcareNotes: profile.retirement_healthcare_notes ?? null,
    retirementIncomeNotes: profile.retirement_income_notes ?? null,
    retirementDebtNotes: profile.retirement_debt_notes ?? null,
    retirementFamilyNotes: profile.retirement_family_notes ?? null,
  };
}

export function mapRetirement(data: ApiRetirement, me: ApiMe) {
  return retirementViewSchema.safeParse({
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
    profile: mapRetirementProfile(data.profile),
    retirementContribution: data.retirement_contribution,
    accounts: (data.retirement_accounts ?? []).map((account) => ({
      id: account.id,
      name: account.name,
      accountType: account.account_type,
      institution: account.institution ?? null,
      currentBalance: account.current_balance,
      isManual: account.is_manual,
    })),
    plaidStatus: data.plaid_status,
  });
}
