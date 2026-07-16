"use client";

import {
  passwordResetConfirmRequestSchema,
  passwordResetConfirmResultSchema,
  passwordResetTokenResultSchema,
} from "@clearpath/validation";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FormEvent, useEffect, useState } from "react";

import { PasswordRequirements } from "../../password-requirements";

function errorMessage(payload: unknown, fallback: string): string {
  if (payload && typeof payload === "object" && "message" in payload) {
    const message = (payload as { message?: unknown }).message;
    if (typeof message === "string" && message.trim()) return message;
  }
  return fallback;
}

export function ResetPasswordForm({ token }: { token: string }) {
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [valid, setValid] = useState(false);
  const [email, setEmail] = useState<string | null>(null);
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmation, setShowConfirmation] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void (async () => {
      try {
        const response = await fetch(`/api/auth/password-reset/${encodeURIComponent(token)}`, { cache: "no-store" });
        const payload: unknown = await response.json();
        if (!active) return;
        if (!response.ok) {
          setFormError(errorMessage(payload, "That password reset link is invalid or expired."));
          return;
        }
        const result = passwordResetTokenResultSchema.safeParse(payload);
        if (!result.success || !result.data.valid) {
          setFormError("That password reset link is invalid or expired.");
          return;
        }
        setValid(true);
        setEmail(result.data.email);
      } catch {
        if (active) setFormError("ClearPath is temporarily unavailable. Please try again.");
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => { active = false; };
  }, [token]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);
    const formData = new FormData(event.currentTarget);
    const parsed = passwordResetConfirmRequestSchema.safeParse({
      password: formData.get("password"),
      confirm_password: formData.get("confirm_password"),
    });
    if (!parsed.success) {
      setFormError(parsed.error.issues[0]?.message ?? "Check your new password.");
      return;
    }
    setSubmitting(true);
    try {
      const response = await fetch(`/api/auth/password-reset/${encodeURIComponent(token)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(parsed.data),
      });
      const payload: unknown = await response.json();
      if (!response.ok) {
        setFormError(errorMessage(payload, "We could not reset your password. Please request a new link."));
        return;
      }
      const result = passwordResetConfirmResultSchema.safeParse(payload);
      if (!result.success) {
        setFormError("ClearPath returned an unexpected reset response. Please try again.");
        return;
      }
      router.push("/login?password_reset=1");
      router.refresh();
    } catch {
      setFormError("ClearPath is temporarily unavailable. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) return <div className="alert alert-info" role="status">Checking your reset link...</div>;
  if (!valid) {
    return (
      <>
        <div className="alert alert-error" role="alert">{formError ?? "That password reset link is invalid or expired."}</div>
        <p className="auth-footnote"><Link href="/forgot-password">Request A New Reset Link</Link></p>
      </>
    );
  }
  return (
    <form onSubmit={handleSubmit} noValidate aria-describedby={formError ? "reset-password-error" : undefined}>
      {formError ? <div className="alert alert-error" id="reset-password-error" role="alert">{formError}</div> : null}
      <div className="form-group">
        <label className="form-label" htmlFor="reset-password">New Password</label>
        <div className="password-input-wrap">
          <input id="reset-password" type={showPassword ? "text" : "password"} name="password" className="form-input" placeholder="At least 12 characters" required autoComplete="new-password" aria-describedby="reset-account-email" disabled={submitting} />
          <button type="button" className="password-toggle" aria-label={showPassword ? "Hide new password" : "Show new password"} onClick={() => setShowPassword((visible) => !visible)}>{showPassword ? "Hide" : "Show"}</button>
        </div>
        <span id="reset-account-email" className="sr-only">Password for {email}</span>
        <PasswordRequirements />
      </div>
      <div className="form-group">
        <label className="form-label" htmlFor="reset-confirm-password">Confirm New Password</label>
        <div className="password-input-wrap">
          <input id="reset-confirm-password" type={showConfirmation ? "text" : "password"} name="confirm_password" className="form-input" required autoComplete="new-password" disabled={submitting} />
          <button type="button" className="password-toggle" aria-label={showConfirmation ? "Hide password confirmation" : "Show password confirmation"} onClick={() => setShowConfirmation((visible) => !visible)}>{showConfirmation ? "Hide" : "Show"}</button>
        </div>
      </div>
      <button type="submit" className="btn btn-primary btn-lg full-button" disabled={submitting}>
        {submitting ? "Resetting Password..." : "Reset Password"}
      </button>
    </form>
  );
}
