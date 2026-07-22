import type { components } from "@clearpath/api-client";
import { billingViewSchema, pricingViewSchema } from "@clearpath/validation";

type ApiPlans = components["schemas"]["BillingPlansResponse"];
type ApiUserState = components["schemas"]["UserBillingStateResponse"];
// The generated feedback-options tuples widen to string[][]; the exact pair
// shape is enforced by Zod (billingViewSchema) at runtime.
type ApiFeedbackOptions = { reasons: string[][]; feature_expectation_reasons: string[][]; broken_features: string[][] };
type ApiMe = components["schemas"]["MeResponse"];
type ApiPlan = components["schemas"]["BillingPlanResponse"];
type ApiTutorial = components["schemas"]["UpgradeTutorialItemResponse"];

export function mapPlan(plan: ApiPlan) {
  return {
    key: plan.key,
    name: plan.name,
    amountCents: plan.amount_cents,
    currency: plan.currency,
    billingInterval: plan.billing_interval,
    priceDisplay: plan.price_display,
    intervalDisplay: plan.interval_display,
    trialPeriodDays: plan.trial_period_days,
    features: plan.features ?? [],
    priceConfigured: plan.price_configured,
  };
}

export function mapSession(me: ApiMe) {
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
    featureAccess: (me.feature_access ?? []).map((row) => ({
      feature: row.feature,
      enabled: row.enabled,
      hidden: row.hidden,
      requiredPlan: row.required_plan,
    })),
  };
}

export function mapPricing(plans: ApiPlans, me: ApiMe | null) {
  const policy = plans.pricing_policy;
  return pricingViewSchema.safeParse({
    session: me ? mapSession(me) : null,
    plans: (plans.plans ?? []).map(mapPlan),
    pricingPolicy: {
      title: policy.title,
      version: policy.version,
      effectiveDate: policy.effective_date,
      cancellationTerms: policy.cancellation_terms,
      paymentCollection: policy.payment_collection,
    },
  });
}

function mapTutorial(item: ApiTutorial) {
  return { title: item.title, body: item.body, target: item.target ?? null, cta: item.cta ?? null };
}

function mapUserState(state: ApiUserState) {
  return {
    selectedPlan: state.selected_plan ?? null,
    billingStatus: state.billing_status,
    hasStripeCustomer: state.has_stripe_customer,
    hasStripeSubscription: state.has_stripe_subscription,
    stripeCurrentPeriodEnd: state.stripe_current_period_end ?? null,
    billingPriceId: state.billing_price_id ?? null,
    config: state.config,
  };
}

export function mapBilling(
  plans: ApiPlans,
  me: ApiMe,
  userState: ApiUserState | null,
  feedbackOptions: ApiFeedbackOptions | null,
) {
  return billingViewSchema.safeParse({
    session: mapSession(me),
    plans: (plans.plans ?? []).map(mapPlan),
    billingConfig: plans.billing_status,
    pricingPolicy: plans.pricing_policy,
    freeTierSignupsEnabled: plans.free_tier_signups_enabled,
    upgradeTutorials: {
      basic: (plans.upgrade_tutorials?.basic ?? []).map(mapTutorial),
      premium: (plans.upgrade_tutorials?.premium ?? []).map(mapTutorial),
    },
    canManageBilling: me.primary_account_holder,
    userState: userState ? mapUserState(userState) : null,
    feedbackOptions: feedbackOptions
      ? {
          reasons: feedbackOptions.reasons,
          featureExpectationReasons: feedbackOptions.feature_expectation_reasons,
          brokenFeatures: feedbackOptions.broken_features,
        }
      : null,
  });
}
