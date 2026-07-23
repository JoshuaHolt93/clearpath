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

export const appFeatureAccessSchema = z.object({
  feature: z.string(),
  enabled: z.boolean(),
  hidden: z.boolean(),
  requiredPlan: z.string(),
});

export const signedInSessionSchema = z.object({
  ownerUserId: z.number().int(),
  householdName: z.string().nullable(),
  selectedPlan: z.string(),
  billingStatus: z.string(),
  planDisplayName: z.string(),
  primaryAccountHolder: z.boolean(),
  subject: z.object({
    id: z.number().int(),
    subjectType: z.enum(["user", "household_member"]),
    email: z.string().email(),
    displayName: z.string(),
    firstName: z.string(),
    avatarInitial: z.string().length(1),
    householdRole: z.string().nullable(),
  }),
  featureAccess: z.array(appFeatureAccessSchema),
});

export type SignedInSession = z.infer<typeof signedInSessionSchema>;

const monthlyBudgetRowSchema = z.object({
  kind: z.string(),
  categoryKind: z.string(),
  categoryId: z.number().int().nullable(),
  label: z.string(),
  category: z.string(),
  groupKey: z.string(),
  planned: z.number(),
  actual: z.number(),
  remaining: z.number(),
  progressPercent: z.number(),
  progressStatus: z.string(),
  anchorId: z.string(),
  transactionIds: z.array(z.number().int()),
  transactionCount: z.number().int(),
  suggestionMatchCount: z.number().int(),
  sortOrder: z.number().int().nullable(),
  canRemoveBudget: z.boolean(),
  actualLabel: z.string(),
  plannedLabel: z.string(),
  adjustLabel: z.string(),
  amortizationAction: z.object({
    action: z.enum(["open", "create"]),
    fixedExpenseItemId: z.number().int().nullable(),
    label: z.string(),
    hint: z.string().nullable(),
  }).nullable(),
});

const monthlyBudgetSectionSchema = z.object({
  label: z.string(),
  kind: z.string(),
  description: z.string(),
  empty: z.string(),
  rows: z.array(monthlyBudgetRowSchema),
  planned: z.number(),
  actual: z.number(),
  transactionIds: z.array(z.number().int()),
  transactionCount: z.number().int(),
});

export const monthlyBudgetsViewSchema = z.object({
  session: signedInSessionSchema,
  monthName: z.string(),
  today: z.string(),
  onboardingComplete: z.boolean(),
  budgetView: z.enum(["list", "grouped"]),
  budgetGrouped: z.boolean(),
  budgetSort: z.enum(["custom", "amount_desc", "amount_asc", "category_az", "category_za"]),
  budgetDragEnabled: z.boolean(),
  budgetSelectedMonth: z.string(),
  budgetCurrentMonth: z.string(),
  budgetMonthValue: z.string(),
  budgetMonthLabel: z.string(),
  budgetIsCurrentMonth: z.boolean(),
  budgetHistoryMode: z.boolean(),
  totalBudgetPlanned: z.number(),
  totalBudgetActual: z.number(),
  totalBudgetRemaining: z.number(),
  expectedCashFlow: z.number(),
  budgetSections: z.array(monthlyBudgetSectionSchema),
  suggestedBudgetSections: z.array(z.object({
    label: z.string(),
    kind: z.string(),
    rows: z.array(monthlyBudgetRowSchema),
  })),
  unassignedBudgetRows: z.array(monthlyBudgetRowSchema),
  categoryLabelOptions: z.array(z.string()),
  budgetGroupOptions: z.array(z.object({
    key: z.string(),
    label: z.string(),
    description: z.string(),
  })),
  budgetSortOptions: z.record(z.string(), z.string()),
});

export type MonthlyBudgetsView = z.infer<typeof monthlyBudgetsViewSchema>;

const planningFrequencySchema = z.enum(["once", "weekly", "biweekly", "semimonthly", "monthly", "quarterly", "annual"]);
const planningWeekdaySchema = z.number().int().min(0).max(6);

const fixedExpenseItemSchema = z.object({
  id: z.number().int(),
  name: z.string(),
  amount: z.number(),
  dueDay: z.number().int().nullable(),
  startDate: z.string(),
  frequency: z.string(),
  daysOfWeek: z.string().nullable(),
  secondDate: z.string().nullable(),
  secondDayOfMonth: z.number().int().nullable(),
  monthlyWeekNumbers: z.string().nullable(),
  monthlyWeekday: z.number().int().nullable(),
  categoryLabel: z.string().nullable(),
  isLoan: z.boolean(),
  notes: z.string().nullable(),
  monthlyAmount: z.number().nullable(),
});

const variableExpenseItemSchema = z.object({
  id: z.number().int(),
  name: z.string(),
  amount: z.number(),
  frequency: z.string(),
  useSpecificDate: z.boolean(),
  specificDate: z.string().nullable(),
  daysOfWeek: z.string().nullable(),
  categoryLabel: z.string().nullable(),
  notes: z.string().nullable(),
  monthlyAmount: z.number().nullable(),
});

const forecastItemSchema = z.object({
  id: z.number().int(),
  itemDate: z.string(),
  description: z.string(),
  amount: z.number(),
  itemType: z.enum(["income", "expense"]),
  categoryLabel: z.string().nullable(),
  notes: z.string().nullable(),
});

const recurringTemplateSchema = z.object({
  id: z.number().int(),
  name: z.string(),
  amount: z.number(),
  itemType: z.enum(["income", "expense"]),
  frequency: z.string(),
  startDate: z.string(),
  secondDate: z.string().nullable(),
  daysOfWeek: z.string().nullable(),
  secondDayOfMonth: z.number().int().nullable(),
  monthlyWeekNumbers: z.string().nullable(),
  monthlyWeekday: z.number().int().nullable(),
  categoryLabel: z.string().nullable(),
  notes: z.string().nullable(),
  incomeReplacement: z.boolean(),
  incomeBasis: z.string().nullable(),
  incomeType: z.string().nullable(),
  paycheckCadence: z.string().nullable(),
  incomeNextPayDate: z.string().nullable(),
  hourlyHoursPerWeek: z.number(),
  additionalIncomeAmount: z.number(),
  additionalIncomeFrequency: z.string(),
  taxState: z.string().nullable(),
  taxFilingStatus: z.string().nullable(),
  includePayrollTaxes: z.boolean(),
  monthlyAmount: z.number().nullable(),
});

const planningProfileSchema = z.object({
  householdName: z.string().nullable(),
  incomeAmount: z.number().nullable(),
  incomeAmountDisplay: z.number().nullable(),
  monthlyIncome: z.number().nullable(),
  incomeBasis: z.string().nullable(),
  incomeType: z.string().nullable(),
  incomeFrequency: z.string().nullable(),
  paycheckCadence: z.string().nullable(),
  nextPayDate: z.string().nullable(),
  paycheckSecondDate: z.string().nullable(),
  paycheckDaysOfWeek: z.string().nullable(),
  paycheckSecondDayOfMonth: z.number().int().nullable(),
  paycheckMonthlyWeekNumbers: z.string().nullable(),
  paycheckMonthlyWeekday: z.number().int().nullable(),
  hourlyHoursPerWeek: z.number().nullable(),
  additionalIncomeAmount: z.number().nullable(),
  additionalIncomeFrequency: z.string().nullable(),
  taxState: z.string().nullable(),
  taxFilingStatus: z.string().nullable(),
  includePayrollTaxes: z.boolean().nullable(),
  notes: z.string().nullable(),
});

export const monthlyQuickPlanningViewSchema = z.object({
  session: signedInSessionSchema,
  monthName: z.string(),
  today: z.string(),
  quickSort: z.enum(["amount_desc", "amount_asc", "name_asc", "name_desc", "timing_asc", "timing_desc", "category_az", "category_za"]),
  quickSortOptions: z.record(z.string(), z.string()),
  totalBudgetPlanned: z.number(),
  fixedTotal: z.number(),
  variablePlanTotal: z.number(),
  quickCashRemainingIncome: z.number(),
  quickCashRemainingExpenses: z.number(),
  quickCashWeekChange: z.number(),
  quickCashWeekEndBalance: z.number(),
  quickCashProjection: z.object({
    endDate: z.string(),
    endBalance: z.number(),
    balanceAnchor: z.object({
      balance: z.number(),
      checkingBalance: z.number(),
      accountCount: z.number().int(),
      checkingAccountCount: z.number().int(),
      usesCashAccounts: z.boolean(),
      includedAccounts: z.array(z.object({
        id: z.number().int(),
        name: z.string(),
        institution: z.string().nullable(),
        accountType: z.string(),
        balance: z.number(),
        mask: z.string().nullable(),
        cashProjectionRole: z.string(),
      })),
    }),
    lowestBalance: z.object({ date: z.string(), balance: z.number() }),
  }).nullable(),
  cashProjectionAccountRows: z.array(z.object({
    accountId: z.number().int(),
    name: z.string(),
    institution: z.string().nullable(),
    accountType: z.string(),
    balance: z.number(),
    mask: z.string().nullable(),
    role: z.enum(["auto", "include", "exclude"]),
    included: z.boolean(),
    statusLabel: z.string(),
    statusClass: z.string(),
    statusDetail: z.string(),
  })),
  quickWorksheetRows: z.array(z.object({
    name: z.string(),
    subtitle: z.string(),
    timing: z.string(),
    category: z.string(),
    amount: z.number(),
    actionLabel: z.string(),
    readonly: z.boolean(),
    itemType: z.string(),
    itemId: z.number().int().nullable(),
  })),
  fixedItems: z.array(fixedExpenseItemSchema),
  variableItems: z.array(variableExpenseItemSchema),
  forecastItems: z.array(forecastItemSchema),
  recurringTemplates: z.array(recurringTemplateSchema),
  categoryLabelOptions: z.array(z.string()),
  profile: planningProfileSchema,
  planIncome: z.number(),
  incomeTypeOptions: z.record(z.string(), z.string()),
  incomeBasisOptions: z.record(z.string(), z.string()),
  paycheckCadenceOptions: z.record(z.string(), z.string()),
  taxFilingStatusOptions: z.record(z.string(), z.string()),
  stateOptions: z.record(z.string(), z.string()),
  recurringFrequencyOptions: z.record(z.string(), z.string()),
  weekdayOptions: z.record(z.string(), z.string()),
  monthlyWeekOptions: z.record(z.string(), z.string()),
});

export type MonthlyQuickPlanningView = z.infer<typeof monthlyQuickPlanningViewSchema>;

const forecastMovementSchema = z.object({
  date: z.string(),
  description: z.string(),
  amount: z.number(),
  itemType: z.enum(["income", "expense"]),
  source: z.string(),
  sourceId: z.union([z.number(), z.string()]).nullable(),
  categoryLabel: z.string().nullable(),
  notes: z.string().nullable(),
});

const forecastMonthSchema = z.object({
  monthStart: z.string(),
  monthName: z.string(),
  baselineIncome: z.number(),
  fixedExpenses: z.number(),
  plannedSavings: z.number(),
  plannedDebt: z.number(),
  plannedTaxes: z.number(),
  plannedRetirement: z.number(),
  plannedVariable: z.number(),
  plannedIncome: z.number(),
  plannedExpenses: z.number(),
  oneTimeIncome: z.number(),
  oneTimeExpenses: z.number(),
  forecastIncomeTotal: z.number(),
  forecastExpenseTotal: z.number(),
  plannedBuffer: z.number(),
  startingCash: z.number(),
  endingCash: z.number(),
  forecastItems: z.array(forecastMovementSchema),
});

export const monthlyForecastViewSchema = z.object({
  session: signedInSessionSchema,
  today: z.string(),
  forecastMonths: z.array(forecastMonthSchema).length(3),
  forecastItems: z.array(forecastItemSchema),
  categoryLabelOptions: z.array(z.string()),
});

export type MonthlyForecastView = z.infer<typeof monthlyForecastViewSchema>;

const incomePlanningProfileSchema = planningProfileSchema.extend({
  taxAdditionalLabel: z.string().nullable(),
  taxAdditionalType: z.enum(["amount", "percent"]).nullable(),
  taxAdditionalRate: z.number().nullable(),
  taxAdditionalMonthlyAmount: z.number().nullable(),
});

const taxEstimateSchema = z.object({
  annualGrossIncome: z.number(),
  taxableIncome: z.number(),
  federalIncomeTax: z.number(),
  stateIncomeTax: z.number(),
  socialSecurityTax: z.number(),
  medicareTax: z.number(),
  additionalMedicareTax: z.number(),
  additionalTaxLabel: z.string(),
  additionalTaxType: z.enum(["amount", "percent"]),
  additionalTaxRate: z.number(),
  additionalTaxAnnual: z.number(),
  additionalTaxMonthly: z.number(),
  annualTotal: z.number(),
  monthlyTotal: z.number(),
  filingStatus: z.string(),
  state: z.string().nullable(),
  stateRate: z.number(),
  stateMethod: z.string(),
  stateTaxableIncome: z.number(),
  stateStandardDeduction: z.number(),
  statePersonalExemption: z.number(),
  stateCredit: z.number(),
  stateBrackets: z.array(z.array(z.number().nullable())),
  stateNote: z.string(),
  stateSourceUrl: z.string().nullable(),
  federalBrackets: z.array(z.array(z.number().nullable())),
  standardDeduction: z.number(),
});

export const monthlyIncomePlanningViewSchema = z.object({
  session: signedInSessionSchema,
  today: z.string(),
  profile: incomePlanningProfileSchema,
  planIncome: z.number(),
  futureIncomeTemplates: z.array(recurringTemplateSchema),
  taxEstimate: taxEstimateSchema,
  taxesEnabled: z.boolean(),
  incomeTypeOptions: z.record(z.string(), z.string()),
  incomeBasisOptions: z.record(z.string(), z.string()),
  paycheckCadenceOptions: z.record(z.string(), z.string()),
  taxFilingStatusOptions: z.record(z.string(), z.string()),
  stateOptions: z.record(z.string(), z.string()),
  recurringFrequencyOptions: z.record(z.string(), z.string()),
  weekdayOptions: z.record(z.string(), z.string()),
  monthlyWeekOptions: z.record(z.string(), z.string()),
});

export type MonthlyIncomePlanningView = z.infer<typeof monthlyIncomePlanningViewSchema>;

export const planningAmountInputSchema = z.object({
  monthlyTarget: z.number().positive("Enter a positive planned cash amount."),
});

export const fixedExpenseInputSchema = z.object({
  name: z.string().trim().min(1, "Enter an expense name."),
  amount: z.number().positive("Enter a positive expense amount."),
  frequency: planningFrequencySchema,
  startDate: z.string().min(1, "Choose a start date."),
  secondDate: z.string().nullable().optional(),
  daysOfWeek: z.array(planningWeekdaySchema).default([]),
  recurringMonthlyWeekNumbers: z.array(z.number().int().min(1).max(5)).default([]),
  recurringMonthlyWeekday: planningWeekdaySchema.nullable().optional(),
  categoryLabel: z.string().trim().nullable().optional(),
  entryContext: z.string().nullable().optional(),
  notes: z.string().trim().nullable().optional(),
});

export const variableExpenseInputSchema = z.object({
  name: z.string().trim().min(1, "Enter an expense bucket."),
  amount: z.number().positive("Enter a positive expense amount."),
  frequency: planningFrequencySchema,
  useSpecificDate: z.boolean(),
  specificDate: z.string().nullable().optional(),
  daysOfWeek: z.array(planningWeekdaySchema).default([]),
  categoryLabel: z.string().trim().nullable().optional(),
  notes: z.string().trim().nullable().optional(),
});

export const forecastItemInputSchema = z.object({
  itemDate: z.string().min(1, "Choose a date."),
  description: z.string().trim().min(1, "Enter a description."),
  amount: z.number().positive("Enter a positive amount."),
  itemType: z.enum(["income", "expense"]),
  categoryLabel: z.string().trim().nullable().optional(),
  notes: z.string().trim().nullable().optional(),
});

export const recurringTemplateInputSchema = z.object({
  name: z.string().trim().min(1, "Enter a recurring item name."),
  amount: z.number().positive("Enter a positive amount."),
  itemType: z.enum(["income", "expense"]),
  frequency: planningFrequencySchema,
  startDate: z.string().min(1, "Choose a start date."),
  secondDate: z.string().nullable().optional(),
  recurringDaysOfWeek: z.array(planningWeekdaySchema).default([]),
  recurringMonthlyWeekNumbers: z.array(z.number().int().min(1).max(5)).default([]),
  recurringMonthlyWeekday: planningWeekdaySchema.nullable().optional(),
  categoryLabel: z.string().trim().nullable().optional(),
  notes: z.string().trim().nullable().optional(),
  incomeAdjustment: z.boolean().default(false),
  incomeReplacement: z.boolean().optional(),
  incomeBasis: z.string().optional(),
  incomeType: z.string().optional(),
  paycheckCadence: z.string().optional(),
  incomeNextPayDate: z.string().nullable().optional(),
  incomeAmount: z.number().positive().optional(),
  hourlyHoursPerWeek: z.number().min(0).nullable().optional(),
  additionalIncomeAmount: z.number().min(0).nullable().optional(),
  additionalIncomeFrequency: z.string().optional(),
  taxState: z.string().nullable().optional(),
  taxFilingStatus: z.string().optional(),
  includePayrollTaxes: z.boolean().optional(),
});

export const planningDeleteInputSchema = z.object({ confirm: z.literal(true) });

export const cashProjectionRoleInputSchema = z.object({
  cashProjectionRole: z.enum(["auto", "include", "exclude"]),
});

export const cashProjectionQueryInputSchema = z.object({
  month: z.string().nullable().optional(),
  horizon: z.enum(["week", "1m", "3m", "6m", "custom"]).nullable().optional(),
  view: z.enum(["calendar", "list", "graph"]).default("calendar"),
  startDate: z.string().nullable().optional(),
  endDate: z.string().nullable().optional(),
});

export const cashProjectionPreferenceInputSchema = z.object({
  defaultHorizon: z.enum(["week", "1m", "3m", "6m"]),
});

export const cashProjectionCalendarFeedInputSchema = z.object({
  action: z.enum(["enable", "reset", "disable"]),
});

export const cashProjectionAutoRecurringInputSchema = cashProjectionQueryInputSchema.extend({
  action: z.enum(["ignore", "save"]),
  name: z.string().trim().nullable().optional(),
  amount: z.number().positive().nullable().optional(),
  frequency: planningFrequencySchema.nullable().optional(),
  scheduleStartDate: z.string().nullable().optional(),
  secondDate: z.string().nullable().optional(),
  recurringDaysOfWeek: z.array(planningWeekdaySchema).default([]),
  recurringMonthlyWeekNumbers: z.array(z.number().int().min(1).max(5)).default([]),
  recurringMonthlyWeekday: planningWeekdaySchema.nullable().optional(),
  categoryLabel: z.string().trim().nullable().optional(),
  notes: z.string().trim().nullable().optional(),
});

const cashProjectionEventSchema = z.object({
  date: z.string(),
  description: z.string(),
  amount: z.number(),
  itemType: z.string(),
  source: z.string(),
  categoryLabel: z.string().nullable(),
  notes: z.string().nullable(),
  sourceId: z.union([z.number(), z.string()]).nullable(),
  signedAmount: z.number().nullable(),
  accountName: z.string().nullable(),
  pending: z.boolean(),
});

const cashProjectionAccountSchema = z.object({
  id: z.number().int(),
  name: z.string(),
  institution: z.string().nullable(),
  accountType: z.string(),
  balance: z.number(),
  mask: z.string().nullable(),
  cashProjectionRole: z.string(),
});

const cashProjectionAnchorSchema = z.object({
  date: z.string(),
  balance: z.number(),
  checkingBalance: z.number(),
  accountCount: z.number().int(),
  checkingAccountCount: z.number().int(),
  includedAccounts: z.array(cashProjectionAccountSchema),
  usesCashAccounts: z.boolean(),
});

const cashProjectionDaySchema = z.object({
  date: z.string(),
  day: z.number().int(),
  weekday: z.string(),
  isToday: z.boolean(),
  isPast: z.boolean(),
  events: z.array(cashProjectionEventSchema),
  actualEvents: z.array(cashProjectionEventSchema),
  scheduledEvents: z.array(cashProjectionEventSchema),
  actualBalance: z.number().nullable(),
  balanceBasis: z.string(),
  netChange: z.number(),
  actualChange: z.number(),
  scheduledChange: z.number(),
  endingBalance: z.number(),
});

const cashProjectionGraphSchema = z.object({
  points: z.string(),
  zeroAxisPct: z.number(),
  showZeroLine: z.boolean(),
  minValue: z.number(),
  maxValue: z.number(),
  monthMarkers: z.array(z.object({ label: z.string(), axisLabel: z.string(), xPct: z.number() })),
  pointRows: z.array(z.object({
    xPct: z.number(),
    yPct: z.number(),
    dateLabel: z.string(),
    balance: z.number(),
    balanceBasis: z.string(),
  })),
});

const cashProjectionPeriodSchema = z.object({
  month: z.string(),
  monthLabel: z.string(),
  startDate: z.string(),
  endDate: z.string(),
  startBalance: z.number(),
  endBalance: z.number(),
  balanceAnchor: cashProjectionAnchorSchema,
  lowestBalance: z.object({ date: z.string(), balance: z.number() }),
  highestBalance: z.object({ date: z.string(), balance: z.number() }),
  days: z.array(cashProjectionDaySchema),
  weeks: z.array(z.object({
    weekStart: z.string(),
    weekEnd: z.string(),
    days: z.array(cashProjectionDaySchema),
    income: z.number(),
    expenses: z.number(),
    endingBalance: z.number(),
    netChange: z.number(),
  })),
  calendarCells: z.array(cashProjectionDaySchema.nullable()),
  events: z.array(cashProjectionEventSchema),
  trend: z.object({
    currentVariableSpend: z.number(),
    plannedVariableSpend: z.number(),
    averageFirstHalfShare: z.number(),
    affectsProjection: z.boolean(),
    message: z.string(),
  }),
  graph: cashProjectionGraphSchema,
});

export const cashProjectionViewSchema = z.object({
  horizon: z.enum(["week", "1m", "3m", "6m", "custom"]),
  view: z.enum(["calendar", "list", "graph"]),
  projection: cashProjectionPeriodSchema,
  projectionRange: z.object({
    startMonth: z.string(),
    startDate: z.string(),
    endDate: z.string(),
    months: z.number().int(),
    projections: z.array(cashProjectionPeriodSchema),
    days: z.array(cashProjectionDaySchema),
    events: z.array(cashProjectionEventSchema),
    startBalance: z.number(),
    endBalance: z.number(),
    balanceAnchor: cashProjectionAnchorSchema,
    lowestBalance: z.object({ date: z.string(), balance: z.number() }),
    highestBalance: z.object({ date: z.string(), balance: z.number() }),
    graph: cashProjectionGraphSchema,
  }),
  previousMonth: z.string(),
  nextMonth: z.string(),
  customStart: z.string(),
  customEnd: z.string(),
  customMinDate: z.string(),
  customMaxDate: z.string(),
  projectionMinMonth: z.string(),
  projectionMaxMonth: z.string(),
  accountRows: z.array(z.object({
    accountId: z.number().int(),
    name: z.string(),
    institution: z.string().nullable(),
    accountType: z.string(),
    balance: z.number(),
    mask: z.string().nullable(),
    role: z.enum(["auto", "include", "exclude"]),
    included: z.boolean(),
    statusLabel: z.string(),
    statusClass: z.string(),
    statusDetail: z.string(),
  })),
  detectedRecurring: z.array(z.object({
    detectionKey: z.string(),
    name: z.string(),
    amount: z.number(),
    frequency: z.string(),
    startDate: z.string(),
    secondDayOfMonth: z.number().int().nullable(),
    categoryLabel: z.string().nullable(),
    notes: z.string().nullable(),
    lastSeen: z.string(),
  })),
  ignoredRecurring: z.array(z.object({
    id: z.number().int(),
    detectionKey: z.string(),
    name: z.string(),
    amount: z.number(),
    frequency: z.string(),
    categoryLabel: z.string().nullable(),
    lastSeen: z.string().nullable(),
    notes: z.string().nullable(),
  })),
  calendarFeed: z.object({
    enabled: z.boolean(),
    feedUrl: z.string().nullable(),
    webcalUrl: z.string().nullable(),
    googleUrl: z.string().nullable(),
    generatedAt: z.string().nullable(),
    historyMonths: z.number().int(),
  }),
  refresh: z.object({ synced: z.number().int(), errors: z.array(z.string()) }).nullable(),
});

export type CashProjectionView = z.infer<typeof cashProjectionViewSchema>;

export const monthlyPlanBaselineInputSchema = z.object({
  baselineScope: z.literal("core").nullable().optional(),
  householdName: z.string().trim().nullable().optional(),
  incomeAmount: z.number().min(0).nullable().optional(),
  incomeBasis: z.string().nullable().optional(),
  incomeType: z.string().nullable().optional(),
  paycheckCadence: z.string().nullable().optional(),
  nextPayDate: z.string().nullable().optional(),
  secondDate: z.string().nullable().optional(),
  recurringDaysOfWeek: z.array(planningWeekdaySchema).default([]),
  recurringMonthlyWeekNumbers: z.array(z.number().int().min(1).max(5)).default([]),
  recurringMonthlyWeekday: planningWeekdaySchema.nullable().optional(),
  hourlyHoursPerWeek: z.number().min(0).nullable().optional(),
  additionalIncomeAmount: z.number().min(0).nullable().optional(),
  additionalIncomeFrequency: z.string().nullable().optional(),
  taxState: z.string().nullable().optional(),
  taxFilingStatus: z.string().nullable().optional(),
  taxAdditionalLabel: z.string().trim().nullable().optional(),
  taxAdditionalType: z.enum(["amount", "percent"]).nullable().optional(),
  taxAdditionalRate: z.number().min(0).nullable().optional(),
  taxAdditionalMonthlyAmount: z.number().min(0).nullable().optional(),
  includePayrollTaxes: z.boolean().nullable().optional(),
  notes: z.string().trim().nullable().optional(),
  view: z.literal("month").default("month"),
  section: z.enum(["tools", "baseline"]).default("tools"),
});

export const budgetCreateInputSchema = z.object({
  categoryLabel: z.string().trim().min(1, "Choose or create a category."),
  monthlyTarget: z.number().positive("Enter a monthly budget amount greater than $0."),
  categoryKind: z.enum(["expense", "income"]),
  budgetMonth: z.string().optional(),
});

export const budgetAmountInputSchema = z.object({
  monthlyTarget: z.number().min(0, "Enter a valid monthly budget amount."),
  budgetMonth: z.string().optional(),
});

export const budgetDeleteInputSchema = z.object({
  budgetMonth: z.string().optional(),
});

export const budgetLayoutInputSchema = z.object({
  budgetMonth: z.string().optional(),
  rows: z.array(z.object({
    categoryId: z.number().int().positive(),
    groupKey: z.string().optional(),
  })).min(1, "No budget rows were provided."),
});

const dashboardPlanDetailSchema = z.object({
  label: z.string(),
  planned: z.number(),
  actual: z.number(),
  source: z.string().nullable(),
});

const dashboardPlanRowSchema = z.object({
  label: z.string(),
  planned: z.number(),
  actual: z.number(),
  type: z.string(),
  details: z.array(dashboardPlanDetailSchema),
});

const dashboardGoalSchema = z.object({
  id: z.number().int(),
  name: z.string(),
  goalType: z.string(),
  progress: z.number(),
  timeline: z.string(),
  currentAmount: z.number(),
  targetAmount: z.number(),
  requiredMonthly: z.number(),
  requiredExtra: z.number(),
  targetDate: z.string().nullable(),
});

const dashboardGuidanceItemSchema = z.object({
  title: z.string(),
  body: z.string(),
  level: z.string(),
  type: z.string(),
  disclaimer: z.string().nullable(),
  action: z.object({ label: z.string(), target: z.string() }).nullable(),
});

export const dashboardViewSchema = z.object({
  session: signedInSessionSchema,
  monthName: z.string(),
  today: z.string(),
  elapsedDays: z.number().int(),
  totalDays: z.number().int(),
  daysLeft: z.number().int(),
  pacePercent: z.number(),
  spendPercent: z.number(),
  showTutorial: z.boolean(),
  metrics: z.object({
    monthIncome: z.number(),
    fixedExpenses: z.number(),
    variableSpend: z.number(),
    safeToSpend: z.number(),
    safeToSpendTarget: z.number(),
    netCashFlow: z.number(),
    onTrackStatus: z.enum(["green", "yellow", "red"]),
    expectedVariableSpend: z.number(),
  }),
  netWorth: z.object({
    assets: z.number(),
    liabilities: z.number(),
    netWorth: z.number(),
  }),
  categoryTotals: z.array(z.object({
    category: z.string(),
    categoryId: z.number().int().nullable(),
    amount: z.number(),
  })),
  goals: z.array(dashboardGoalSchema),
  recentTransactions: z.array(z.object({
    id: z.number().int(),
    postedDate: z.string(),
    description: z.string(),
    amount: z.number(),
    transactionType: z.string(),
    categoryName: z.string().nullable(),
  })),
  planRows: z.array(dashboardPlanRowSchema),
  budgetRemaining: z.number(),
  expectedCashFlow: z.number(),
  insights: z.array(z.object({
    title: z.string(),
    body: z.string(),
    level: z.string(),
    type: z.string(),
    disclaimer: z.string(),
  })),
  dashboardFocus: z.object({
    items: z.array(dashboardGuidanceItemSchema),
    generatedAt: z.string().nullable(),
    message: z.string(),
  }).nullable(),
});

export type DashboardView = z.infer<typeof dashboardViewSchema>;

const analyticsSnapshotSchema = z.object({
  month: z.string(),
  plannedIncome: z.number(),
  plannedFixedExpenses: z.number(),
  plannedVariableExpenses: z.number(),
  plannedSavings: z.number(),
  plannedDebtPayment: z.number(),
  plannedTaxes: z.number(),
  plannedRetirement: z.number(),
  plannedSafeToSpend: z.number(),
  expectedCashFlow: z.number(),
  budgetRemaining: z.number(),
  actualIncome: z.number(),
  actualFixedExpenses: z.number(),
  actualVariableExpenses: z.number(),
  actualTotalExpenses: z.number(),
  netCashFlow: z.number(),
});

const analyticsSubscriptionSchema = z.object({
  id: z.number().int(),
  name: z.string(),
  serviceCategory: z.string(),
  monthlyAmount: z.number(),
  annualAmount: z.number(),
  cycle: z.string(),
  confidence: z.number(),
  status: z.string(),
  replaceable: z.boolean(),
  nextChargeDate: z.string().nullable(),
});

const analyticsSummarySchema = z.object({
  rangeKey: z.string(),
  rangeLabel: z.string(),
  months: z.array(z.string()),
  snapshots: z.array(analyticsSnapshotSchema),
  startDate: z.string(),
  endDate: z.string(),
  totalIncome: z.number(),
  totalSpending: z.number(),
  totalExpectedCashFlow: z.number(),
  totalNetCashFlow: z.number(),
  averageIncome: z.number(),
  averageSpending: z.number(),
  averageNetCashFlow: z.number(),
  maxIncome: z.number(),
  maxSpending: z.number(),
  maxCashFlow: z.number(),
  categoryRows: z.array(z.object({ category: z.string(), categoryId: z.number().int().nullable(), amount: z.number() })),
  subscriptions: z.object({
    subscriptions: z.array(analyticsSubscriptionSchema),
    activeCount: z.number().int(),
    reviewCount: z.number().int(),
    actionCount: z.number().int(),
    manageLinkCount: z.number().int(),
    monthlyTotal: z.number(),
    annualTotal: z.number(),
    potentialSavings: z.number(),
    spendingShare: z.number().int(),
    categoryBreakdown: z.array(z.object({ category: z.string(), amount: z.number(), percent: z.number().int() })),
    opportunities: z.array(z.object({ subscription: analyticsSubscriptionSchema, reason: z.string() })),
    upcoming: z.array(analyticsSubscriptionSchema),
  }),
});

export const analyticsViewSchema = z.object({
  session: signedInSessionSchema,
  summary: analyticsSummarySchema,
  budgetHistorySummary: analyticsSummarySchema,
  debtToIncomeRatio: z.number(),
  rangeOptions: z.record(z.string(), z.string()),
  selectedRange: z.string(),
  endMonth: z.string(),
  selectedHistoryRange: z.string(),
  historyEndMonth: z.string(),
  subscriptionAnalyticsEnabled: z.boolean(),
  subscriptionAnalyticsPlanLabel: z.string(),
  aiCoachEnabled: z.boolean(),
  aiCoachHidden: z.boolean(),
});

export type AnalyticsView = z.infer<typeof analyticsViewSchema>;
export type AnalyticsSummaryView = z.infer<typeof analyticsSummarySchema>;
export type AnalyticsSnapshotView = z.infer<typeof analyticsSnapshotSchema>;

export const goalViewSchema = z.object({
  id: z.number().int(),
  name: z.string(),
  goalType: z.enum(["savings", "debt"]),
  targetAmount: z.number(),
  currentAmount: z.number(),
  monthlyContribution: z.number(),
  targetDate: z.string().nullable(),
  fixedExpenseItemId: z.number().int().nullable(),
  progress: z.number(),
  timeline: z.string(),
  remaining: z.number(),
  requiredMonthly: z.number(),
  requiredExtra: z.number(),
  linkedItem: z.object({ id: z.number().int(), name: z.string() }).nullable(),
});

export const goalsViewSchema = z.object({
  session: signedInSessionSchema,
  goals: z.array(goalViewSchema),
  loanOptions: z.array(z.object({
    fixedExpenseItemId: z.number().int(),
    name: z.string(),
    loanKind: z.string(),
    monthlyPayment: z.number(),
    selectedExtra: z.number(),
    totalMonthly: z.number(),
    principalBalance: z.number(),
    currentBalance: z.number(),
    collateralValue: z.number(),
    selectedScenario: z.string(),
  })),
});

export const goalMutationInputSchema = z.object({
  name: z.string().trim().min(1, "Enter a goal name."),
  goalType: z.enum(["savings", "debt"]),
  targetAmount: z.number().nullable(),
  currentAmount: z.number().nullable(),
  monthlyContribution: z.number().nullable(),
  targetDate: z.string().nullable(),
  fixedExpenseItemId: z.number().int().positive().nullable(),
});

export type GoalView = z.infer<typeof goalViewSchema>;
export type GoalsView = z.infer<typeof goalsViewSchema>;
export type GoalMutationInput = z.infer<typeof goalMutationInputSchema>;

export const plannerGuidanceActionSchema = z.object({
  label: z.string(),
  target: z.string(),
});

export const plannerGuidanceItemSchema = z.object({
  title: z.string(),
  body: z.string(),
  level: z.string(),
  type: z.string(),
  disclaimer: z.string().nullable(),
  action: plannerGuidanceActionSchema.nullable(),
});

export const plannerModelOptionSchema = z.object({
  key: z.string(),
  label: z.string(),
  configured: z.boolean(),
  models: z.array(z.object({ id: z.string(), label: z.string() })),
});

export const plannerUsageSchema = z.object({
  burstCount: z.number().int(),
  dailyCount: z.number().int(),
  monthlyCount: z.number().int(),
  monthlyCostCents: z.number(),
  burstLimit: z.number().int(),
  dailyLimit: z.number().int(),
  monthlyLimit: z.number().int(),
  monthlyCostLimitCents: z.number().int(),
  currentLimitReason: z.string().nullable(),
});

export const plannerGuidanceSchema = z.object({
  source: z.string(),
  provider: z.string(),
  model: z.string(),
  items: z.array(plannerGuidanceItemSchema),
  status: z.string(),
  message: z.string(),
  generatedAt: z.string().nullable(),
  modelOptions: z.array(plannerModelOptionSchema),
  selectedProvider: z.string(),
  selectedModel: z.string(),
  usage: plannerUsageSchema,
});

export const plannerViewSchema = z.object({
  session: signedInSessionSchema,
  guidance: plannerGuidanceSchema,
});

export const plannerPreferenceInputSchema = z.object({
  provider: z.string().trim().min(1, "Choose an AI provider."),
  model: z.string().trim().min(1, "Choose an AI model."),
});

export const plannerPageContextInputSchema = z.object({
  path: z.string(),
  title: z.string(),
  section: z.string(),
  visibleText: z.string(),
  question: z.string(),
});

export const plannerPageContextResponseSchema = z.object({
  source: z.string(),
  provider: z.string(),
  model: z.string(),
  items: z.array(plannerGuidanceItemSchema),
  status: z.string(),
  message: z.string(),
});

export type PlannerGuidance = z.infer<typeof plannerGuidanceSchema>;
export type PlannerGuidanceItem = z.infer<typeof plannerGuidanceItemSchema>;
export type PlannerView = z.infer<typeof plannerViewSchema>;
export type PlannerPageContextInput = z.infer<typeof plannerPageContextInputSchema>;
export type PlannerPageContextResponse = z.infer<typeof plannerPageContextResponseSchema>;

export const loanPlanSummarySchema = z.object({
  fixedExpenseItemId: z.number().int(),
  name: z.string(),
  loanKind: z.string(),
  monthlyPayment: z.number(),
  selectedExtra: z.number(),
  totalMonthly: z.number(),
  principalBalance: z.number(),
  currentBalance: z.number(),
  collateralValue: z.number(),
  selectedScenario: z.string(),
});

export const loanPlanDirectorySchema = z.object({
  session: signedInSessionSchema,
  items: z.array(loanPlanSummarySchema),
  totalDebtMonthly: z.number(),
  totalDebtBalance: z.number(),
  debtToIncomeRatio: z.number(),
  loanCategoryLabelOptions: z.array(z.string()),
  today: z.string(),
  recurringFrequencyOptions: z.record(z.string(), z.string()),
  weekdayOptions: z.record(z.string(), z.string()),
  monthlyWeekOptions: z.record(z.string(), z.string()),
});

export const loanPlanRecordSchema = z.object({
  id: z.number().int(),
  fixedExpenseItemId: z.number().int(),
  loanType: z.string(),
  principalBalance: z.number(),
  collateralValue: z.number(),
  annualInterestRate: z.number(),
  termMonths: z.number().int(),
  termUnitPreference: z.string(),
  regularPayment: z.number(),
  extraPaymentOne: z.number(),
  extraPaymentTwo: z.number(),
  selectedScenario: z.string(),
  notes: z.string().nullable(),
});

export const loanPlanResourceSchema = z.object({
  fixedExpense: z.object({
    id: z.number().int(),
    name: z.string(),
    amount: z.number(),
    frequency: z.string(),
    startDate: z.string(),
    categoryLabel: z.string().nullable(),
    isLoan: z.boolean(),
    monthlyAmount: z.number().nullable(),
  }),
  loanKind: z.string(),
  plan: loanPlanRecordSchema.nullable(),
  scenarios: z.array(z.object({
    key: z.string(), label: z.string(), extraPayment: z.number(), months: z.number().int(),
    years: z.number(), interestPaid: z.number(), payoffPossible: z.boolean(),
  })),
  selectedSchedule: z.array(z.object({
    month: z.number().int(), paymentDate: z.string(), beginningBalance: z.number(), payment: z.number(),
    principal: z.number(), interest: z.number(), endingBalance: z.number(),
  })),
  createdFixedExpense: z.boolean(),
});

export const loanPlanDetailSchema = z.object({
  session: signedInSessionSchema,
  resource: loanPlanResourceSchema,
});

export const loanPlanUpdateInputSchema = z.object({
  principalBalance: z.number().nonnegative(),
  collateralValue: z.number().nonnegative(),
  annualInterestRate: z.number().nonnegative(),
  termValue: z.number().positive("Enter a remaining term."),
  termUnit: z.enum(["months", "years"]),
  regularPayment: z.number().nonnegative(),
  extraPaymentOne: z.number().nonnegative(),
  extraPaymentTwo: z.number().nonnegative(),
  selectedScenario: z.enum(["base", "extra_one", "extra_two"]),
  notes: z.string().trim().nullable(),
});

export const loanPlanScenarioInputSchema = z.object({
  selectedScenario: z.enum(["base", "extra_one", "extra_two"]),
});

export type LoanPlanDirectory = z.infer<typeof loanPlanDirectorySchema>;
export type LoanPlanResource = z.infer<typeof loanPlanResourceSchema>;
export type LoanPlanDetail = z.infer<typeof loanPlanDetailSchema>;
export type LoanPlanUpdateInput = z.infer<typeof loanPlanUpdateInputSchema>;

export const plaidRefreshSummarySchema = z.object({
  synced: z.number().int(),
  errors: z.array(z.string()),
});

const transactionCategorySchema = z.object({
  id: z.number().int(),
  name: z.string(),
  kind: z.string(),
  monthlyTarget: z.number(),
  isDefault: z.boolean(),
  budgetGroupKey: z.string().nullable(),
  budgetSortOrder: z.number().int().nullable(),
  canManage: z.boolean(),
});

const transactionAccountSchema = z.object({
  id: z.number().int(),
  name: z.string(),
  accountType: z.string(),
  institution: z.string().nullable(),
  currentBalance: z.number(),
  isManual: z.boolean(),
  mask: z.string().nullable(),
});

export const transactionViewSchema = z.object({
  id: z.number().int(),
  postedDate: z.string(),
  description: z.string(),
  displayMerchant: z.string(),
  rawDescription: z.string().nullable(),
  amount: z.number(),
  transactionType: z.string(),
  sourceName: z.string().nullable(),
  notes: z.string().nullable(),
  plaidTransactionId: z.string().nullable(),
  plaidCategoryLabel: z.string().nullable(),
  paymentChannelLabel: z.string().nullable(),
  locationSummary: z.string().nullable(),
  pending: z.boolean(),
  category: transactionCategorySchema.nullable(),
  account: transactionAccountSchema.nullable(),
  splits: z.array(z.object({
    id: z.number().int(),
    category: transactionCategorySchema,
    amount: z.number(),
    notes: z.string().nullable(),
  })),
});

export type TransactionView = z.infer<typeof transactionViewSchema>;

export const transactionReviewViewSchema = z.object({
  session: signedInSessionSchema,
  items: z.array(transactionViewSchema),
  total: z.number().int(),
  page: z.number().int().positive(),
  perPage: z.number().int().positive(),
  categories: z.array(transactionCategorySchema),
  accounts: z.array(transactionAccountSchema),
  duplicateSuggestions: z.array(z.object({
    plaidTransactionId: z.number().int(),
    manualTransactionId: z.number().int(),
    score: z.number(),
    confidenceLabel: z.string(),
    plaidTransaction: transactionViewSchema,
    manualTransaction: transactionViewSchema,
  })),
  budgetActions: z.record(z.string(), z.object({
    categoryName: z.string(),
    target: z.number(),
    targetLabel: z.string(),
    hint: z.string(),
  })),
  amortizationActions: z.record(z.string(), z.object({
    action: z.string(),
    fixedExpenseItemId: z.number().int().nullable(),
    label: z.string(),
    hint: z.string().nullable(),
  })),
  recurringTransactionIds: z.array(z.number().int()),
  plaidItems: z.array(z.object({
    id: z.number().int(),
    institutionName: z.string().nullable(),
    status: z.string(),
    lastSyncedAt: z.string().nullable(),
    errorMessage: z.string().nullable(),
    reconnectRequiredAt: z.string().nullable(),
    accounts: z.array(transactionAccountSchema),
  })),
});

export type TransactionReviewView = z.infer<typeof transactionReviewViewSchema>;

export const transactionCategoryUpdateInputSchema = z.object({
  categoryId: z.number().int().positive().nullable(),
  newCategoryName: z.string().trim().max(80).nullable().default(null),
  applyToSimilar: z.boolean().default(true),
  markRecurring: z.boolean().default(false),
  recurringName: z.string().trim().max(160).nullable().default(null),
  recurringStartDate: z.string().nullable().default(null),
  recurringSecondDate: z.string().nullable().default(null),
  recurringFrequency: z.enum(["weekly", "biweekly", "semimonthly", "monthly", "quarterly", "annual"]).default("monthly"),
  recurringDaysOfWeek: z.array(z.number().int().min(0).max(6)).default([]),
  recurringMonthlyWeekNumbers: z.array(z.number().int().min(1).max(5)).default([]),
  recurringMonthlyWeekday: z.number().int().min(0).max(6).nullable().default(null),
}).superRefine((value, context) => {
  if (!value.categoryId && !value.newCategoryName) context.addIssue({ code: "custom", path: ["categoryId"], message: "Choose or create a category." });
  if (value.markRecurring && !value.recurringStartDate) context.addIssue({ code: "custom", path: ["recurringStartDate"], message: "Choose the first expected date." });
});

export type TransactionCategoryUpdateInput = z.infer<typeof transactionCategoryUpdateInputSchema>;

export const transactionSplitsInputSchema = z.object({
  clearSplits: z.boolean().default(false),
  splits: z.array(z.object({ categoryId: z.number().int().positive(), amount: z.number().positive(), notes: z.string().nullable().default(null) })).default([]),
});

export type TransactionSplitsInput = z.infer<typeof transactionSplitsInputSchema>;

export const duplicateMergeInputSchema = z.object({ firstTransactionId: z.number().int().positive(), secondTransactionId: z.number().int().positive() });
export const categoryCreateInputSchema = z.object({ name: z.string().trim().min(1).max(80), kind: z.enum(["expense", "income"]).default("expense"), activateBudget: z.boolean().default(true) });
export const categoryUpdateInputSchema = z.object({ name: z.string().trim().min(1).max(80), kind: z.enum(["expense", "income"]) });
export const categoryDeleteInputSchema = z.object({ replacementCategoryId: z.number().int().positive().nullable().default(null) });

export const transactionImportMappingSchema = z.object({
  date: z.string().min(1),
  description: z.string().min(1),
  amount: z.string().nullable().default(null),
  debit: z.string().nullable().default(null),
  credit: z.string().nullable().default(null),
  account: z.string().nullable().default(null),
});

export const transactionImportPreviewInputSchema = z.object({
  csvText: z.string().min(1),
  mapping: transactionImportMappingSchema.nullable().default(null),
  fallbackAccount: z.string().trim().min(1).default("Imported Account"),
});

export type TransactionImportPreviewInput = z.infer<typeof transactionImportPreviewInputSchema>;

export const transactionImportPreviewViewSchema = z.object({
  stagedImportId: z.string().min(1),
  headers: z.array(z.string()),
  sampleRows: z.array(z.record(z.string(), z.unknown())),
  mapping: transactionImportMappingSchema,
  newTransactions: z.array(z.object({ postedDate: z.string(), description: z.string(), amount: z.number(), transactionType: z.string(), sourceName: z.string(), categoryId: z.number().int().nullable(), categoryName: z.string().nullable() })),
  newCount: z.number().int(),
  duplicateCount: z.number().int(),
});

export type TransactionImportPreviewView = z.infer<typeof transactionImportPreviewViewSchema>;

export const subscriptionEvidenceSchema = z.object({
  id: z.number().int().nullable(),
  date: z.string().nullable(),
  description: z.string().nullable(),
  amount: z.number().nullable(),
});

export const subscriptionViewSchema = z.object({
  id: z.number().int(),
  merchantKey: z.string(),
  name: z.string(),
  category: z.string(),
  serviceCategory: z.string(),
  amount: z.number(),
  monthlyAmount: z.number(),
  annualAmount: z.number(),
  cycle: z.string(),
  cycleDays: z.number().int(),
  confidence: z.number(),
  status: z.string(),
  cancelUrl: z.string().nullable(),
  replaceable: z.boolean(),
  firstSeen: z.string().nullable(),
  lastSeen: z.string().nullable(),
  nextChargeDate: z.string().nullable(),
  notes: z.string().nullable(),
  isManual: z.boolean(),
  cycleIsManual: z.boolean(),
  evidence: z.array(subscriptionEvidenceSchema),
});

export type SubscriptionView = z.infer<typeof subscriptionViewSchema>;

export const subscriptionsViewSchema = z.object({
  session: signedInSessionSchema,
  subscriptions: z.array(subscriptionViewSchema),
  summary: z.object({
    activeCount: z.number().int(),
    reviewCount: z.number().int(),
    actionCount: z.number().int(),
    manageLinkCount: z.number().int(),
    monthlyTotal: z.number(),
    annualTotal: z.number(),
    potentialSavings: z.number(),
    averageConfidence: z.number().int(),
    transactionCount: z.number().int(),
  }),
  categoryBreakdown: z.array(z.object({ category: z.string(), amount: z.number(), percent: z.number().int() })),
  opportunities: z.array(z.object({ subscriptionId: z.number().int(), reason: z.string() })),
  upcomingSubscriptionIds: z.array(z.number().int()),
  statuses: z.record(z.string(), z.string()),
  cycles: z.array(z.string()),
});

export type SubscriptionsView = z.infer<typeof subscriptionsViewSchema>;

export const subscriptionCreateInputSchema = z.object({
  name: z.string().trim().min(1, "Subscription name is required."),
  amount: z.number().positive("Amount must be greater than zero."),
  cycle: z.enum(["Weekly", "Biweekly", "Monthly", "Quarterly", "Annual"]),
  nextChargeDate: z.string().nullable().default(null),
  notes: z.string().trim().nullable().default(null),
});

export const subscriptionUpdateInputSchema = z.object({
  status: z.string().nullable().optional(),
  notes: z.string().nullable().optional(),
  cycle: z.string().nullable().optional(),
  cancelUrl: z.string().nullable().optional(),
}).refine((value) => Object.values(value).some((item) => item !== undefined), "Choose a subscription change.");

export const subscriptionImportInputSchema = z.object({ csvText: z.string().min(1, "Choose a CSV file to scan.") });

export const categoryRuleFieldSchema = z.enum(["description", "account", "amount", "category"]);
export const categoryRuleOperatorSchema = z.enum(["contains", "equals", "starts_with", "ends_with", "not_contains", "gt", "gte", "lt", "lte", "between"]);

export const categoryRuleConditionSchema = z.object({
  field: categoryRuleFieldSchema,
  operator: categoryRuleOperatorSchema,
  value: z.string().trim().min(1, "Enter a condition value."),
  valueSecondary: z.string().trim().default(""),
  group: z.string().default("primary"),
  join: z.enum(["and", "or"]).default("and"),
}).superRefine((condition, context) => {
  if (condition.field === "amount" && condition.operator === "between" && !condition.valueSecondary) {
    context.addIssue({ code: "custom", path: ["valueSecondary"], message: "Enter the upper limit." });
  }
});

const categoryRuleCategorySchema = z.object({
  id: z.number().int(),
  name: z.string(),
  kind: z.string(),
  monthlyTarget: z.number(),
  isDefault: z.boolean(),
  canManage: z.boolean(),
});

export const categoryRuleSchema = z.object({
  id: z.number().int(),
  category: categoryRuleCategorySchema,
  matchText: z.string(),
  matchType: z.string(),
  ruleLogic: z.string(),
  conditions: z.array(categoryRuleConditionSchema).max(4),
  summary: z.string(),
  createdAt: z.string(),
  updatedAt: z.string(),
  appliedCount: z.number().int().nullable(),
});

export const categoryRulesViewSchema = z.object({
  session: signedInSessionSchema,
  rules: z.array(categoryRuleSchema),
  categories: z.array(categoryRuleCategorySchema),
});

export type CategoryRuleCondition = z.infer<typeof categoryRuleConditionSchema>;
export type CategoryRuleView = z.infer<typeof categoryRuleSchema>;
export type CategoryRulesView = z.infer<typeof categoryRulesViewSchema>;

export const categoryRuleMutationInputSchema = z.object({
  categoryId: z.number().int().positive("Choose a category."),
  conditions: z.array(categoryRuleConditionSchema).min(1, "Add at least one condition.").max(4, "Rules can have up to four conditions."),
});

export const categoryRuleDeleteInputSchema = z.object({ confirm: z.literal(true) });

export const householdMemberViewSchema = z.object({
  id: z.number().int(),
  email: z.string(),
  displayName: z.string().nullable(),
  role: z.string().nullable(),
  status: z.string(),
  acceptedAt: z.string().nullable(),
});

export const householdInviteViewSchema = z.object({
  id: z.number().int(),
  email: z.string(),
  role: z.string(),
  status: z.string(),
  expiresAt: z.string().nullable(),
});

export const settingsViewSchema = z.object({
  session: signedInSessionSchema,
  email: z.string(),
  displayName: z.string().nullable(),
  householdName: z.string().nullable(),
  rulesCount: z.number().int(),
  categoryRows: z.array(z.object({
    id: z.number().int(),
    name: z.string(),
    kind: z.string(),
    monthlyTarget: z.number(),
    canManage: z.boolean(),
    usage: z.record(z.string(), z.number()),
  })),
  // PlaidStatusResponse is {ready, sdk_installed, crypto_installed,
  // has_credentials, has_encryption_key, environment} -- there is no
  // `configured`. Requiring it made every real response fail validation, so the
  // tab rendered only "data did not match the expected contract".
  plaidStatus: z.object({ ready: z.boolean() }).passthrough(),
  pushMfa: z.object({ available: z.boolean() }).passthrough(),
  mfaEnabled: z.boolean(),
  mfaPreferredMethod: z.string(),
  mfaPushEnabled: z.boolean(),
  billingStatus: z.record(z.string(), z.unknown()),
  feedbackOptions: z.object({
    reasons: z.array(z.tuple([z.string(), z.string()])),
    featureExpectationReasons: z.array(z.tuple([z.string(), z.string()])),
    brokenFeatures: z.array(z.tuple([z.string(), z.string()])),
  }),
  householdRoleOptions: z.record(z.string(), z.string()),
  householdMembers: z.array(householdMemberViewSchema),
  pendingHouseholdInvites: z.array(householdInviteViewSchema),
  canManageHouseholdAccess: z.boolean(),
  householdAccessIsShared: z.boolean(),
  ethicsAcknowledgedAt: z.string().nullable(),
  ethicsPolicyVersion: z.string().nullable(),
  accountDeleteConfirmation: z.string(),
  accountDeleteBillingBlocked: z.boolean(),
});

export const passwordChangeInputSchema = z.object({
  currentPassword: z.string().min(1, "Enter your current password."),
  newPassword: z.string().min(1, "Enter a new password."),
  confirmPassword: z.string().min(1, "Confirm the new password."),
});

export const householdNameInputSchema = z.object({
  householdName: z.string().trim(),
});

export const mfaPreferenceInputSchema = z.object({
  mfaPreferredMethod: z.enum(["totp", "push"]),
});

export const householdInviteInputSchema = z.object({
  inviteEmail: z.string().trim().min(1, "Enter an email to invite."),
  inviteRole: z.enum(["editor", "viewer"]),
});

export const householdInviteCreateResultSchema = z.object({
  invite: householdInviteViewSchema,
  emailSent: z.boolean(),
  fallbackInviteUrl: z.string().nullable(),
  deliveryReason: z.string().nullable(),
});

export const householdMemberRoleInputSchema = z.object({
  memberRole: z.enum(["editor", "viewer"]),
});

export const accountDeleteInputSchema = z.object({
  currentPassword: z.string().min(1, "Enter your current password."),
  confirmation: z.string().trim().min(1, "Type the confirmation phrase."),
});

export type SettingsView = z.infer<typeof settingsViewSchema>;
export type HouseholdMemberView = z.infer<typeof householdMemberViewSchema>;
export type HouseholdInviteView = z.infer<typeof householdInviteViewSchema>;
export type PasswordChangeInput = z.infer<typeof passwordChangeInputSchema>;
export type HouseholdInviteInput = z.infer<typeof householdInviteInputSchema>;
export type AccountDeleteInput = z.infer<typeof accountDeleteInputSchema>;

export const billingPlanSchema = z.object({
  key: z.string(),
  name: z.string(),
  amountCents: z.number().int(),
  currency: z.string(),
  billingInterval: z.string(),
  priceDisplay: z.string(),
  intervalDisplay: z.string(),
  trialPeriodDays: z.number().int(),
  features: z.array(z.string()),
  priceConfigured: z.boolean(),
});

export const pricingPolicySchema = z.object({
  title: z.string(),
  version: z.string(),
  effectiveDate: z.string(),
  cancellationTerms: z.string(),
  paymentCollection: z.string(),
});

export const pricingViewSchema = z.object({
  session: signedInSessionSchema.nullable(),
  plans: z.array(billingPlanSchema),
  pricingPolicy: pricingPolicySchema,
});

export const helpViewSchema = z.object({
  session: signedInSessionSchema,
});

export const billingTutorialItemSchema = z.object({
  title: z.string(),
  body: z.string(),
  target: z.string().nullable(),
  cta: z.string().nullable(),
});

export const billingUserStateSchema = z.object({
  selectedPlan: z.string().nullable(),
  billingStatus: z.string(),
  hasStripeCustomer: z.boolean(),
  hasStripeSubscription: z.boolean(),
  stripeCurrentPeriodEnd: z.string().nullable(),
  billingPriceId: z.string().nullable(),
  config: z.record(z.string(), z.unknown()),
});

export const billingViewSchema = z.object({
  session: signedInSessionSchema,
  plans: z.array(billingPlanSchema),
  billingConfig: z.record(z.string(), z.unknown()),
  pricingPolicy: z.record(z.string(), z.unknown()),
  freeTierSignupsEnabled: z.boolean(),
  upgradeTutorials: z.object({
    basic: z.array(billingTutorialItemSchema),
    premium: z.array(billingTutorialItemSchema),
  }),
  canManageBilling: z.boolean(),
  userState: billingUserStateSchema.nullable(),
  feedbackOptions: z.object({
    reasons: z.array(z.tuple([z.string(), z.string()])),
    featureExpectationReasons: z.array(z.tuple([z.string(), z.string()])),
    brokenFeatures: z.array(z.tuple([z.string(), z.string()])),
  }).nullable(),
});

export const billingPlanSelectionInputSchema = z.object({
  plan: z.string().min(1, "Choose a plan."),
  promotionCode: z.string().trim().nullable().optional(),
});

export const billingCancellationInputSchema = z.object({
  reason: z.string().nullable().optional(),
  featureExpectationReason: z.string().nullable().optional(),
  brokenFeatures: z.array(z.string()).optional(),
  description: z.string().nullable().optional(),
  notifyWhenAddressed: z.boolean().optional(),
});

export type BillingView = z.infer<typeof billingViewSchema>;
export type BillingPlan = z.infer<typeof billingPlanSchema>;
export type PricingView = z.infer<typeof pricingViewSchema>;
export type HelpView = z.infer<typeof helpViewSchema>;
export type BillingPlanSelectionInput = z.infer<typeof billingPlanSelectionInputSchema>;
export type BillingCancellationInput = z.infer<typeof billingCancellationInputSchema>;

export const feedbackViewSchema = z.object({
  session: signedInSessionSchema,
  options: z.object({
    reasons: z.array(z.tuple([z.string(), z.string()])),
    featureExpectationReasons: z.array(z.tuple([z.string(), z.string()])),
    brokenFeatures: z.array(z.tuple([z.string(), z.string()])),
  }),
});

export const feedbackInputSchema = z.object({
  reason: z.string().min(1, "Choose the main reason."),
  featureExpectationReason: z.string().nullable().optional(),
  brokenFeatures: z.array(z.string()).optional(),
  description: z.string().nullable().optional(),
  notifyWhenAddressed: z.boolean().optional(),
});

export const controlEvaluationSchema = z.object({
  id: z.number().int(),
  controlId: z.string(),
  controlName: z.string(),
  status: z.enum(["pass", "warn", "fail"]),
  evidence: z.string(),
  evaluatedAt: z.string(),
});

export const complianceViewSchema = z.object({
  session: signedInSessionSchema,
  isAdmin: z.boolean(),
  evaluations: z.array(controlEvaluationSchema),
  controls: z.array(z.object({
    id: z.string(),
    name: z.string(),
    description: z.string(),
    ownerRole: z.string().nullable(),
    reviewCadence: z.string().nullable(),
  })),
});

export type FeedbackView = z.infer<typeof feedbackViewSchema>;
export type FeedbackInput = z.infer<typeof feedbackInputSchema>;
export type ComplianceView = z.infer<typeof complianceViewSchema>;
export type ControlEvaluationView = z.infer<typeof controlEvaluationSchema>;

export const retirementAccountSchema = z.object({
  id: z.number().int(),
  name: z.string(),
  accountType: z.string(),
  institution: z.string().nullable(),
  currentBalance: z.number(),
  isManual: z.boolean(),
});

export const retirementProfileSchema = z.object({
  retirementEnabled: z.boolean(),
  retirementHasEmployerPlan: z.boolean(),
  retirementEmployerWithheld: z.boolean(),
  retirementHasPersonalPlan: z.boolean(),
  retirementMonthlyContribution: z.number(),
  retirementPersonalMonthlyContribution: z.number(),
  retirementLifestyleNotes: z.string().nullable(),
  retirementLocationNotes: z.string().nullable(),
  retirementHealthcareNotes: z.string().nullable(),
  retirementIncomeNotes: z.string().nullable(),
  retirementDebtNotes: z.string().nullable(),
  retirementFamilyNotes: z.string().nullable(),
});

export const retirementViewSchema = z.object({
  session: signedInSessionSchema,
  profile: retirementProfileSchema,
  retirementContribution: z.number(),
  accounts: z.array(retirementAccountSchema),
  // PlaidStatusResponse is {ready, sdk_installed, crypto_installed,
  // has_credentials, has_encryption_key, environment} -- there is no
  // `configured`. Requiring it made every real response fail validation, so the
  // tab rendered only "data did not match the expected contract".
  plaidStatus: z.object({ ready: z.boolean() }).passthrough(),
});

export const retirementSurveyInputSchema = z.object({
  retirementEnabled: z.boolean(),
  retirementHasEmployerPlan: z.boolean(),
  retirementEmployerWithheld: z.boolean(),
  retirementHasPersonalPlan: z.boolean(),
  retirementMonthlyContribution: z.number().nonnegative(),
  retirementPersonalMonthlyContribution: z.number().nonnegative(),
});

export const retirementWorksheetInputSchema = z.object({
  retirementLifestyleNotes: z.string(),
  retirementLocationNotes: z.string(),
  retirementHealthcareNotes: z.string(),
  retirementIncomeNotes: z.string(),
  retirementDebtNotes: z.string(),
  retirementFamilyNotes: z.string(),
});

export type RetirementView = z.infer<typeof retirementViewSchema>;
export type RetirementSurveyInput = z.infer<typeof retirementSurveyInputSchema>;
export type RetirementWorksheetInput = z.infer<typeof retirementWorksheetInputSchema>;
