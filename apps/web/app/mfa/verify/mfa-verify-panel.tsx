"use client";

import {
  loginResultSchema,
  mfaChallengeSchema,
  mfaVerifyRequestSchema,
  type MfaChallenge,
} from "@clearpath/validation";
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

export function MfaVerifyPanel() {
  const router = useRouter();
  const [challenge, setChallenge] = useState<MfaChallenge | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    async function loadChallenge() {
      try {
        const response = await fetch("/api/auth/mfa/challenge", { cache: "no-store" });
        const payload: unknown = await response.json();
        if (!response.ok) {
          throw new Error(messageFrom(payload, "Your pending sign-in session is unavailable."));
        }
        const parsed = mfaChallengeSchema.safeParse(payload);
        if (!parsed.success) {
          throw new Error("ClearPath returned an unexpected MFA challenge.");
        }
        if (active) {
          setChallenge(parsed.data);
        }
      } catch (loadError) {
        if (active) {
          setError(loadError instanceof Error ? loadError.message : "ClearPath is temporarily unavailable.");
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    }
    void loadChallenge();
    return () => {
      active = false;
    };
  }, []);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!challenge) {
      return;
    }
    setError(null);

    const formData = new FormData(event.currentTarget);
    const method = challenge.preferredMethod === "email" ? "email" : "totp";
    const parsed = mfaVerifyRequestSchema.safeParse({
      method,
      code: method === "totp" ? formData.get("code") : undefined,
      email_code: method === "email" ? formData.get("email_code") : undefined,
    });
    if (!parsed.success) {
      setError(parsed.error.issues[0]?.message ?? "Check your verification code.");
      return;
    }

    setSubmitting(true);
    try {
      const response = await fetch("/api/auth/mfa/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(parsed.data),
      });
      const payload: unknown = await response.json();
      if (!response.ok) {
        setError(messageFrom(payload, "Your verification code was not accepted."));
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

  if (loading) {
    return <p className="pending-status" role="status">Loading verification options...</p>;
  }

  if (!challenge) {
    return (
      <>
        <div className="alert alert-error" role="alert">{error}</div>
        <p className="panel-footnote"><Link href="/login">Return To Sign In</Link></p>
      </>
    );
  }

  const emailMethod = challenge.preferredMethod === "email";
  const pushMethod = challenge.preferredMethod === "push";
  const methodUnavailable = emailMethod && !challenge.emailAvailable;

  return (
    <>
      {error ? <div className="alert alert-error" role="alert">{error}</div> : null}
      {pushMethod ? (
        <div className="alert alert-warning">
          {challenge.pushAvailable
            ? "Approve the push prompt on your mobile device, or use an authenticator code below."
            : "Push approval is temporarily unavailable. Use your authenticator code to continue."}
        </div>
      ) : null}
      {methodUnavailable ? (
        <div className="alert alert-warning">
          Email code delivery is temporarily unavailable. Use a recovery code to continue.
        </div>
      ) : (
        <>
          {emailMethod ? (
            <p className="panel-intro">
              We sent a short-lived code to <strong>{challenge.email}</strong>. Enter it below to finish signing in.
            </p>
          ) : null}
          <form onSubmit={handleSubmit} noValidate>
            <div className="form-group">
              <label className="form-label" htmlFor="mfa-code">
                {emailMethod ? "Email Verification Code" : "6-Digit Authentication Code"}
              </label>
              <input
                id="mfa-code"
                name={emailMethod ? "email_code" : "code"}
                className="form-input code-input"
                inputMode="numeric"
                autoComplete="one-time-code"
                autoFocus
                disabled={submitting}
                required
              />
            </div>
            <button type="submit" className="btn btn-primary full-button" disabled={submitting}>
              {submitting ? "Verifying..." : "Verify And Continue"}
            </button>
          </form>
        </>
      )}
      <p className="panel-footnote">
        Lost access to your MFA method? <Link href="/mfa/recovery">Use A Recovery Code</Link>
      </p>
    </>
  );
}
