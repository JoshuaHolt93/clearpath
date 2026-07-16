export const AUTH_NEXT_STEP_PATHS = {
  mfa_verify: "/mfa/verify",
  mfa_setup: "/mfa/setup",
  select_plan: "/select-plan",
  onboarding: "/onboarding",
  dashboard: "/dashboard",
} as const;

export type AuthNextStep = keyof typeof AUTH_NEXT_STEP_PATHS;
