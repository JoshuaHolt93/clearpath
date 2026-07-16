"use client";

import { loginResultSchema, mfaRecoveryRequestSchema } from "@clearpath/validation";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FormEvent, useEffect, useState } from "react";

import { AUTH_NEXT_STEP_PATHS } from "@/lib/auth-navigation";

function messageFrom(payload: unknown, fallback: string): string {
  if (payload && typeof payload === "object" && "message" in payload) {
    const message = (payload as { message?: unknown }).message;
    if (typeof message === "string" && message.trim()) {
      return message;
    }
  }
  return fallback;
}

export function MfaRecoveryPanel() {
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    async function checkChallenge() {
      try {
        const response = await fetch("/api/auth/mfa/recovery", { cache: "no-store" });
        const payload: unknown = await response.json();
        if (!response.ok) {
          throw new Error(messageFrom(payload, "Your pending sign-in session is unavailable."));
        }
        if (
          !payload ||
          typeof payload !== "object" ||
          !("available" in payload) ||
          (payload as { available?: unknown }).available !== true
        ) {
          throw new Error("Recovery-code verification is unavailable.");
        }
        if (active) {
          setReady(true);
        }
      } catch (loadError) {
        if (active) {
          setError(loadError instanceof Error ? loadError.message : "ClearPath is temporarily unavailable.");
        }
      }
    }
    void checkChallenge();
    return () => {
      active = false;
    };
  }, []);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    const formData = new FormData(event.currentTarget);
    const parsed = mfaRecoveryRequestSchema.safeParse({
      recovery_code: formData.get("recovery_code"),
    });
    if (!parsed.success) {
      setError(parsed.error.issues[0]?.message ?? "Check your recovery code.");
      return;
    }

    setSubmitting(true);
    try {
      const response = await fetch("/api/auth/mfa/recovery", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(parsed.data),
      });
      const payload: unknown = await response.json();
      if (!response.ok) {
        setError(messageFrom(payload, "Your recovery code was not accepted."));
        return;
      }
      const result = loginResultSchema.safeParse(payload);
      if (!result.success) {
        setError("ClearPath returned an unexpected sign-in response.");
        return;
      }
      router.push(AUTH_NEXT_STEP_PATHS[result.data.nextStep]);
      router.refresh();
    } catch {
      setError("ClearPath is temporarily unavailable. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  if (!ready && !error) {
    return <p className="pending-status" role="status">Checking your pending sign-in...</p>;
  }

  if (!ready) {
    return (
      <>
        <div className="alert alert-error" role="alert">{error}</div>
        <p className="panel-footnote"><Link href="/login">Return To Sign In</Link></p>
      </>
    );
  }

  return (
    <>
      {error ? <div className="alert alert-error" role="alert">{error}</div> : null}
      <form onSubmit={handleSubmit} noValidate>
        <div className="form-group">
          <label className="form-label" htmlFor="recovery-code">Recovery Code</label>
          <input
            id="recovery-code"
            type="text"
            name="recovery_code"
            className="form-input code-input"
            placeholder="XXXX-XXXX-XXXX"
            autoComplete="one-time-code"
            autoCapitalize="characters"
            autoFocus
            disabled={submitting}
            required
          />
        </div>
        <button type="submit" className="btn btn-primary full-button" disabled={submitting}>
          {submitting ? "Checking Code..." : "Use Recovery Code"}
        </button>
      </form>
      <p className="panel-footnote">
        Have your authenticator code? <Link href="/mfa/verify">Return To MFA Verification</Link>
      </p>
    </>
  );
}
