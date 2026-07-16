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
