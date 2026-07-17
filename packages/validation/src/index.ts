import { z } from "zod";

export const loginRequestSchema = z.object({
  email: z.string().trim().email("Enter a valid email address.").transform((value) => value.toLowerCase()),
  password: z.string().min(1, "Password is required."),
  stay_signed_in: z.boolean().default(false),
});

export type LoginRequest = z.infer<typeof loginRequestSchema>;

export const loginResultSchema = z.object({
  nextStep: z.enum(["mfa_verify", "mfa_setup", "select_plan", "onboarding", "dashboard"]),
});

export const registerRequestSchema = z.object({
  display_name: z.string().trim().min(1, "Your name is required."),
  household_name: z.string().trim().transform((value) => value || null),
  email: z.string().trim().email("Enter a valid email address.").transform((value) => value.toLowerCase()),
  password: z.string().min(12, "Password must be at least 12 characters long."),
  policy_acknowledgement: z.boolean().refine((accepted) => accepted, {
    message: "Please review and accept the ClearPath policies to create an account.",
  }),
});

export type RegisterRequest = z.infer<typeof registerRequestSchema>;
export const registerResultSchema = loginResultSchema;

export const passwordResetRequestSchema = z.object({
  email: z.string().trim().email("Enter a valid email address.").transform((value) => value.toLowerCase()),
});

export type PasswordResetRequest = z.infer<typeof passwordResetRequestSchema>;

export const passwordResetRequestResultSchema = z.object({
  message: z.string().min(1),
  resetUrl: z.string().min(1).nullable(),
});

export const passwordResetTokenResultSchema = z.object({
  valid: z.boolean(),
  email: z.string().email().nullable(),
});

export const passwordResetConfirmRequestSchema = z
  .object({
    password: z.string().min(12, "Password must be at least 12 characters long."),
    confirm_password: z.string().min(1, "Confirm your new password."),
  })
  .superRefine((value, context) => {
    if (value.password !== value.confirm_password) {
      context.addIssue({
        code: "custom",
        path: ["confirm_password"],
        message: "New password and confirmation did not match.",
      });
    }
  });

export type PasswordResetConfirmRequest = z.infer<typeof passwordResetConfirmRequestSchema>;

export const passwordResetConfirmResultSchema = z.object({ ok: z.literal(true) });

export const householdInviteTokenSchema = z.object({
  valid: z.boolean(),
  email: z.string().email().nullable(),
  householdName: z.string().nullable(),
  role: z.enum(["editor", "viewer"]).nullable(),
});

export type HouseholdInviteToken = z.infer<typeof householdInviteTokenSchema>;

export const householdInviteAcceptRequestSchema = z
  .object({
    display_name: z.string().trim().min(1, "Your name is required."),
    password: z.string().min(12, "Password must be at least 12 characters long."),
    confirm_password: z.string().min(1, "Confirm your password."),
    policy_acknowledgement: z.boolean().refine((accepted) => accepted, {
      message: "Please accept the ClearPath Terms, Privacy Policy, and Ethics Policy to use shared access.",
    }),
  })
  .superRefine((value, context) => {
    if (value.password !== value.confirm_password) {
      context.addIssue({
        code: "custom",
        path: ["confirm_password"],
        message: "Password and confirmation did not match.",
      });
    }
  });

export type HouseholdInviteAcceptRequest = z.infer<typeof householdInviteAcceptRequestSchema>;
export const householdInviteAcceptResultSchema = loginResultSchema;

export const mfaChallengeSchema = z.object({
  subjectType: z.enum(["user", "household_member"]),
  email: z.string().email(),
  preferredMethod: z.enum(["totp", "email", "push", "none"]),
  pushAvailable: z.boolean(),
  emailAvailable: z.boolean(),
  emailChallengeSent: z.boolean(),
});

export type MfaChallenge = z.infer<typeof mfaChallengeSchema>;

export const mfaVerifyRequestSchema = z
  .object({
    method: z.enum(["totp", "email"]),
    code: z.string().trim().optional(),
    email_code: z.string().trim().optional(),
  })
  .superRefine((value, context) => {
    const code = value.method === "email" ? value.email_code : value.code;
    if (!code) {
      context.addIssue({
        code: "custom",
        message: value.method === "email" ? "Email verification code is required." : "Authentication code is required.",
      });
    }
  });

export type MfaVerifyRequest = z.infer<typeof mfaVerifyRequestSchema>;

export const mfaRecoveryRequestSchema = z.object({
  recovery_code: z.string().trim().min(1, "Recovery code is required."),
});

export const mfaSetupSchema = z.object({
  subjectType: z.enum(["user", "household_member"]),
  email: z.string().email(),
  mfaEnabled: z.boolean(),
  preferredMethod: z.enum(["totp", "email", "push", "none"]),
  setupKey: z.string().min(1),
  provisioningUri: z.string().startsWith("otpauth://"),
  mobileSetupToken: z.string().min(1),
  pushAvailable: z.boolean(),
  pushProvider: z.string(),
  pushConfigured: z.boolean(),
  sharedAccessTotpOnly: z.boolean(),
  emailAvailable: z.boolean(),
});

export type MfaSetup = z.infer<typeof mfaSetupSchema>;

export const mfaSetupConfirmRequestSchema = z
  .object({
    action: z.enum(["verify_totp", "skip", "confirm_email_code"]),
    code: z.string().trim().optional(),
    email_code: z.string().trim().optional(),
    mfa_push_opt_in: z.boolean().default(false),
  })
  .superRefine((value, context) => {
    if (value.action === "verify_totp" && !value.code) {
      context.addIssue({ code: "custom", message: "Authentication code is required." });
    }
    if (value.action === "confirm_email_code" && !value.email_code) {
      context.addIssue({ code: "custom", message: "Email verification code is required." });
    }
  });

export type MfaSetupConfirmRequest = z.infer<typeof mfaSetupConfirmRequestSchema>;

export const mfaSetupResultSchema = loginResultSchema.extend({
  recoveryCodes: z.array(z.string()).nullable(),
});

export const mfaEmailCodeResultSchema = z.object({
  sent: z.boolean(),
  reason: z.string().nullable(),
});

export const mfaMobileSetupSchema = z.object({
  provisioningUri: z.string().startsWith("otpauth://").nullable(),
  expired: z.boolean(),
  email: z.string().email().nullable(),
  subjectType: z.enum(["user", "household_member"]).nullable(),
});

export const mfaPushStartSchema = z.object({
  pushAvailable: z.boolean(),
  fallback: z.literal("totp"),
  authorizationUrl: z.string().url().nullable(),
  reason: z.string().nullable(),
});

export const onboardingIncomePlanRequestSchema = z.object({
  income_amount: z.number(),
  monthly_income: z.number().optional(),
  income_basis: z.enum(["take_home", "gross"]),
  income_type: z.enum(["salary", "hourly"]),
  paycheck_cadence: z.enum(["annual", "monthly", "semimonthly", "biweekly", "weekly", "irregular"]),
  next_pay_date: z.string().nullable(),
  second_date: z.string().nullable(),
  recurring_days_of_week: z.array(z.number().int().min(0).max(6)),
  recurring_monthly_week_numbers: z.array(z.number().int().min(1).max(5)),
  recurring_monthly_weekday: z.number().int().min(0).max(6).nullable(),
  hourly_hours_per_week: z.number(),
  fixed_expenses: z.number().default(0),
  variable_expenses: z.number().default(0),
  additional_income_amount: z.number().default(0),
  additional_income_frequency: z.enum(["weekly", "biweekly", "semimonthly", "monthly", "quarterly", "annual"]),
  planned_savings_contribution: z.number().default(0),
  planned_debt_payment: z.number().default(0),
  target_investment_contribution: z.number().default(0),
  tax_filing_status: z.string().min(1),
  tax_state: z.string().nullable(),
  include_payroll_taxes: z.boolean(),
  notes: z.string().default(""),
});

export type OnboardingIncomePlanRequest = z.infer<typeof onboardingIncomePlanRequestSchema>;

const onboardingProfileSchema = z.object({
  householdName: z.string().nullable(),
  incomeAmount: z.number().nullable(),
  incomeAmountDisplay: z.number().nullable(),
  monthlyIncome: z.number().nullable(),
  incomeBasis: z.string().nullable(),
  incomeType: z.string().nullable(),
  paycheckCadence: z.string().nullable(),
  nextPayDate: z.string().nullable(),
  paycheckSecondDate: z.string().nullable(),
  paycheckDaysOfWeek: z.string().nullable(),
  paycheckMonthlyWeekNumbers: z.string().nullable(),
  paycheckMonthlyWeekday: z.number().nullable(),
  hourlyHoursPerWeek: z.number().nullable(),
  additionalIncomeAmount: z.number().nullable(),
  additionalIncomeFrequency: z.string().nullable(),
  taxState: z.string().nullable(),
  taxFilingStatus: z.string().nullable(),
  includePayrollTaxes: z.boolean().nullable(),
  notes: z.string().nullable(),
});

export const onboardingStatusSchema = z.object({
  activeStep: z.enum(["connect", "income", "transactions"]),
  incomeReady: z.boolean(),
  hasBank: z.boolean(),
  setupComplete: z.boolean(),
  profile: onboardingProfileSchema,
  today: z.string(),
  plaidStatus: z.object({
    ready: z.boolean(),
    sdkInstalled: z.boolean(),
    cryptoInstalled: z.boolean(),
    hasCredentials: z.boolean(),
    hasEncryptionKey: z.boolean(),
    environment: z.string(),
  }),
  plaidItems: z.array(
    z.object({
      id: z.number().int(),
      institutionName: z.string().nullable(),
      status: z.string(),
      lastSyncedAt: z.string().nullable(),
    }),
  ),
  transactions: z.array(
    z.object({
      id: z.number().int(),
      displayMerchant: z.string(),
      postedDate: z.string(),
      amount: z.number(),
      accountName: z.string().nullable(),
      sourceName: z.string().nullable(),
      categoryId: z.number().int().nullable(),
    }),
  ),
  categories: z.array(
    z.object({
      id: z.number().int(),
      name: z.string(),
      kind: z.string(),
    }),
  ),
  autoCategorizedCount: z.number().int(),
  seededBudgetCount: z.number().int(),
  message: z.string().nullable(),
  nextPath: z.string().nullable(),
  incomeBasisOptions: z.record(z.string(), z.string()),
  incomeTypeOptions: z.record(z.string(), z.string()),
  paycheckCadenceOptions: z.record(z.string(), z.string()),
  recurringFrequencyOptions: z.record(z.string(), z.string()),
  weekdayOptions: z.record(z.string(), z.string()),
  monthlyWeekOptions: z.record(z.string(), z.string()),
  taxFilingStatusOptions: z.record(z.string(), z.string()),
  stateOptions: z.record(z.string(), z.string()),
});

export type OnboardingStatus = z.infer<typeof onboardingStatusSchema>;

export const plaidLinkTokenResultSchema = z.object({
  linkToken: z.string().min(1),
  consentToken: z.string().min(1),
});

export const plaidExchangeRequestSchema = z.object({
  public_token: z.string().min(1, "Plaid did not return a public token."),
  metadata: z.record(z.string(), z.unknown()).default({}),
  consent_token: z.string().min(1).nullable(),
});

export const plaidLinkEventSchema = z.object({
  event_name: z.string().max(80),
  error: z.record(z.string(), z.unknown()).nullable().optional(),
  metadata: z.record(z.string(), z.unknown()).default({}),
});

export const onboardingCategorySelectionSchema = z.object({
  category_id: z.number().int().positive("Choose a category."),
});
