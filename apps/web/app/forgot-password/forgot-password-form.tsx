"use client";

import { passwordResetRequestResultSchema, passwordResetRequestSchema } from "@clearpath/validation";
import { type FormEvent, useState } from "react";

function errorMessage(payload: unknown): string {
  if (payload && typeof payload === "object" && "message" in payload) {
    const message = (payload as { message?: unknown }).message;
    if (typeof message === "string" && message.trim()) return message;
  }
  return "We could not request a reset link. Please try again.";
}

export function ForgotPasswordForm() {
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [resetUrl, setResetUrl] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);
    setNotice(null);
    setResetUrl(null);
    const formData = new FormData(event.currentTarget);
    const parsed = passwordResetRequestSchema.safeParse({ email: formData.get("email") });
    if (!parsed.success) {
      setFormError(parsed.error.issues[0]?.message ?? "Enter a valid email address.");
      return;
    }
    setSubmitting(true);
    try {
      const response = await fetch("/api/auth/password-reset/request", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(parsed.data),
      });
      const payload: unknown = await response.json();
      if (!response.ok) {
        setFormError(errorMessage(payload));
        return;
      }
      const result = passwordResetRequestResultSchema.safeParse(payload);
      if (!result.success) {
        setFormError("ClearPath returned an unexpected reset response. Please try again.");
        return;
      }
      setNotice(result.data.message);
      setResetUrl(result.data.resetUrl);
    } catch {
      setFormError("ClearPath is temporarily unavailable. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} noValidate aria-describedby={formError ? "forgot-password-error" : undefined}>
      {formError ? <div className="alert alert-error" id="forgot-password-error" role="alert">{formError}</div> : null}
      {notice ? <div className="alert alert-info" role="status">{notice}</div> : null}
      <div className="form-group">
        <label className="form-label" htmlFor="forgot-password-email">Email Address</label>
        <input id="forgot-password-email" type="email" name="email" className="form-input" placeholder="you@example.com" required autoComplete="email" autoCapitalize="none" disabled={submitting} />
      </div>
      <button type="submit" className="btn btn-primary btn-lg full-button" disabled={submitting}>
        {submitting ? "Sending Reset Link..." : "Send Reset Link"}
      </button>
      {resetUrl ? (
        <div className="local-reset-link">
          Local reset link: <a href={resetUrl}>Reset Password</a>
        </div>
      ) : null}
    </form>
  );
}
