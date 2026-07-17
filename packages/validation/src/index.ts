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
