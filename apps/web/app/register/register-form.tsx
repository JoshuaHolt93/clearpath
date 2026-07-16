"use client";

import { registerRequestSchema, registerResultSchema } from "@clearpath/validation";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FormEvent, useState } from "react";

import { PasswordRequirements } from "../password-requirements";
import { AUTH_NEXT_STEP_PATHS } from "@/lib/auth-navigation";

function errorMessage(payload: unknown): string {
  if (payload && typeof payload === "object" && "message" in payload) {
    const message = (payload as { message?: unknown }).message;
    if (typeof message === "string" && message.trim()) return message;
  }
  return "We could not create your account. Please check your details and try again.";
}

export function RegisterForm() {
  const router = useRouter();
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);
    const formData = new FormData(event.currentTarget);
    const parsed = registerRequestSchema.safeParse({
      display_name: formData.get("display_name"),
      household_name: formData.get("household_name"),
      email: formData.get("email"),
      password: formData.get("password"),
      policy_acknowledgement: formData.get("policy_acknowledgement") === "on",
    });
    if (!parsed.success) {
      setFormError(parsed.error.issues[0]?.message ?? "Check your account details.");
      return;
    }
    setSubmitting(true);
    try {
      const response = await fetch("/api/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(parsed.data),
      });
      const payload: unknown = await response.json();
      if (!response.ok) {
        setFormError(errorMessage(payload));
        return;
      }
      const result = registerResultSchema.safeParse(payload);
      if (!result.success) {
        setFormError("ClearPath returned an unexpected account response. Please try again.");
        return;
      }
      router.push(AUTH_NEXT_STEP_PATHS[result.data.nextStep]);
      router.refresh();
    } catch {
      setFormError("ClearPath is temporarily unavailable. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} autoComplete="on" noValidate aria-describedby={formError ? "register-error" : undefined}>
      {formError ? <div className="alert alert-error" id="register-error" role="alert">{formError}</div> : null}
      <div className="form-group">
        <label className="form-label" htmlFor="register-name">Your Name</label>
        <input id="register-name" name="display_name" className="form-input" placeholder="Jordan Parker" required autoComplete="name" disabled={submitting} />
      </div>
      <div className="form-group">
        <label className="form-label" htmlFor="register-household">Household Name</label>
        <input id="register-household" name="household_name" className="form-input" placeholder="The Parker household" disabled={submitting} />
      </div>
      <div className="form-group">
        <label className="form-label" htmlFor="register-email">Email Address</label>
        <input id="register-email" type="email" name="email" className="form-input" placeholder="you@example.com" required autoComplete="email" autoCapitalize="none" disabled={submitting} />
      </div>
      <div className="form-group">
        <label className="form-label" htmlFor="register-password">Password</label>
        <div className="password-input-wrap">
          <input id="register-password" type={showPassword ? "text" : "password"} name="password" className="form-input" placeholder="At least 12 characters" required autoComplete="new-password" disabled={submitting} />
          <button type="button" className="password-toggle" aria-label={showPassword ? "Hide password" : "Show password"} onClick={() => setShowPassword((visible) => !visible)}>
            {showPassword ? "Hide" : "Show"}
          </button>
        </div>
        <PasswordRequirements />
      </div>
      <label className="checkbox-row policy-acknowledgement">
        <input type="checkbox" name="policy_acknowledgement" required disabled={submitting} />
        <span>
          I have read and agree to the <Link href="/ethics" target="_blank" rel="noopener">Ethics Policy</Link>,{" "}
          <Link href="/privacy" target="_blank" rel="noopener">Privacy Policy</Link>, and{" "}
          <Link href="/terms" target="_blank" rel="noopener">Terms &amp; Conditions</Link>.
        </span>
      </label>
      <button type="submit" className="btn btn-primary btn-lg full-button" disabled={submitting}>
        {submitting ? "Creating Account..." : "Create Account"}
      </button>
    </form>
  );
}
