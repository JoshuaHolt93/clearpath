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
