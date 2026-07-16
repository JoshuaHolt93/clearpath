"use client";

import { loginRequestSchema, loginResultSchema } from "@clearpath/validation";
import { useRouter } from "next/navigation";
import { type FormEvent, useState } from "react";

import { AUTH_NEXT_STEP_PATHS } from "@/lib/auth-navigation";

function errorMessage(payload: unknown): string {
  if (payload && typeof payload === "object" && "message" in payload) {
    const message = (payload as { message?: unknown }).message;
    if (typeof message === "string" && message.trim()) {
      return message;
    }
  }
  return "We could not sign you in. Please check your details and try again.";
}

export function LoginForm() {
  const router = useRouter();
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);

    const formData = new FormData(event.currentTarget);
    const parsed = loginRequestSchema.safeParse({
      email: formData.get("email"),
      password: formData.get("password"),
      stay_signed_in: formData.get("stay_signed_in") === "on",
    });
    if (!parsed.success) {
      setFormError(parsed.error.issues[0]?.message ?? "Check the highlighted fields.");
      return;
    }

    setSubmitting(true);
    try {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(parsed.data),
      });
      const payload: unknown = await response.json();
      if (!response.ok) {
        setFormError(errorMessage(payload));
        return;
      }

      const result = loginResultSchema.safeParse(payload);
      if (!result.success) {
        setFormError("ClearPath returned an unexpected sign-in response. Please try again.");
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
    <form onSubmit={handleSubmit} autoComplete="on" noValidate aria-describedby={formError ? "login-error" : undefined}>
      {formError ? (
        <div className="alert alert-error" id="login-error" role="alert">
          {formError}
        </div>
      ) : null}
      <div className="form-group">
        <label className="form-label" htmlFor="login-email">Email Address</label>
        <input
          id="login-email"
          type="email"
          name="email"
          className="form-input"
          placeholder="you@example.com"
          required
          autoComplete="username"
          autoCapitalize="none"
          disabled={submitting}
        />
      </div>
      <div className="form-group">
        <label className="form-label" htmlFor="login-password">Password</label>
        <div className="password-input-wrap">
          <input
            id="login-password"
            type={showPassword ? "text" : "password"}
            name="password"
            className="form-input"
            placeholder="Password"
            required
            autoComplete="current-password"
            disabled={submitting}
          />
          <button
            type="button"
            className="password-toggle"
            aria-label={showPassword ? "Hide password" : "Show password"}
            onClick={() => setShowPassword((visible) => !visible)}
          >
            {showPassword ? "Hide" : "Show"}
          </button>
        </div>
      </div>
      <label className="toggle-control">
        <input type="checkbox" name="stay_signed_in" disabled={submitting} />
        <span className="toggle-track" aria-hidden="true"><span className="toggle-thumb" /></span>
        <span className="toggle-label">Stay signed in on this device</span>
      </label>
      <button type="submit" className="btn btn-primary btn-lg full-button" disabled={submitting}>
        {submitting ? "Signing In..." : "Sign In"}
      </button>
    </form>
  );
}
