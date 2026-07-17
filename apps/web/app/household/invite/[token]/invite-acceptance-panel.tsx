"use client";

import {
  householdInviteAcceptRequestSchema,
  householdInviteAcceptResultSchema,
  householdInviteTokenSchema,
  type HouseholdInviteToken,
} from "@clearpath/validation";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FormEvent, useEffect, useState } from "react";

import { PasswordRequirements } from "../../../password-requirements";
import { PublicAuthShell } from "../../../public-auth-shell";
import { AUTH_NEXT_STEP_PATHS } from "@/lib/auth-navigation";

function errorMessage(payload: unknown, fallback: string): string {
  if (payload && typeof payload === "object" && "message" in payload) {
    const message = (payload as { message?: unknown }).message;
    if (typeof message === "string" && message.trim()) return message;
  }
  return fallback;
}

export function InviteAcceptancePanel({ token }: { token: string }) {
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [invite, setInvite] = useState<HouseholdInviteToken | null>(null);
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmation, setShowConfirmation] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void (async () => {
      try {
        const response = await fetch(`/api/household-invites/${encodeURIComponent(token)}`, { cache: "no-store" });
        const payload: unknown = await response.json();
        if (!active) return;
        if (!response.ok) {
          setFormError(errorMessage(payload, "That household invite is expired or has already been used."));
          return;
        }
        const result = householdInviteTokenSchema.safeParse(payload);
        if (!result.success || !result.data.valid) {
          setFormError("That household invite is expired or has already been used.");
          return;
        }
        setInvite(result.data);
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
    const parsed = householdInviteAcceptRequestSchema.safeParse({
      display_name: formData.get("display_name"),
      password: formData.get("password"),
      confirm_password: formData.get("confirm_password"),
      policy_acknowledgement: formData.get("policy_acknowledgement") === "on",
    });
    if (!parsed.success) {
      setFormError(parsed.error.issues[0]?.message ?? "Check your invitation details.");
      return;
    }
    setSubmitting(true);
    try {
      const response = await fetch(`/api/household-invites/${encodeURIComponent(token)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(parsed.data),
      });
      const payload: unknown = await response.json();
      if (!response.ok) {
        setFormError(errorMessage(payload, "We could not accept this household invite."));
        return;
      }
      const result = householdInviteAcceptResultSchema.safeParse(payload);
      if (!result.success) {
        setFormError("ClearPath returned an unexpected invitation response. Please try again.");
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

  const title = invite ? `Join ${invite.householdName || "This Household"}` : "Accept Household Invite";
  return (
    <PublicAuthShell
      headingId="household-invite-title"
      title={title}
      subtitle="Create your own password to access the shared ClearPath household."
    >
      {loading ? <div className="alert alert-info" role="status">Checking your invitation...</div> : null}
      {!loading && !invite ? (
        <>
          <div className="alert alert-error" role="alert">{formError ?? "That household invite is expired or has already been used."}</div>
          <p className="auth-footnote"><Link href="/login">Back To Sign In</Link></p>
        </>
      ) : null}
      {invite ? (
        <>
          <form onSubmit={handleSubmit} noValidate aria-describedby={formError ? "household-invite-error" : undefined}>
            {formError ? <div className="alert alert-error" id="household-invite-error" role="alert">{formError}</div> : null}
            <div className="form-group">
              <label className="form-label" htmlFor="invite-email">Invite Email</label>
              <input id="invite-email" type="email" className="form-input" value={invite.email ?? ""} readOnly />
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="invite-permission">Permission</label>
              <input id="invite-permission" className="form-input" value={invite.role === "editor" ? "Can Edit" : "View Only"} readOnly />
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="invite-display-name">Your Name</label>
              <input id="invite-display-name" name="display_name" className="form-input" placeholder="Jordan Parker" autoComplete="name" required disabled={submitting} />
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="household-invite-password">Password</label>
              <div className="password-input-wrap">
                <input id="household-invite-password" type={showPassword ? "text" : "password"} name="password" className="form-input" placeholder="Create password" autoComplete="new-password" required disabled={submitting} />
                <button type="button" className="password-toggle" aria-label={showPassword ? "Hide password" : "Show password"} onClick={() => setShowPassword((visible) => !visible)}>{showPassword ? "Hide" : "Show"}</button>
              </div>
              <PasswordRequirements />
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="household-invite-confirm-password">Confirm Password</label>
              <div className="password-input-wrap">
                <input id="household-invite-confirm-password" type={showConfirmation ? "text" : "password"} name="confirm_password" className="form-input" placeholder="Confirm password" autoComplete="new-password" required disabled={submitting} />
                <button type="button" className="password-toggle" aria-label={showConfirmation ? "Hide password confirmation" : "Show password confirmation"} onClick={() => setShowConfirmation((visible) => !visible)}>{showConfirmation ? "Hide" : "Show"}</button>
              </div>
            </div>
            <label className="checkbox-row policy-acknowledgement">
              <input type="checkbox" name="policy_acknowledgement" required disabled={submitting} />
              <span>
                I agree to the <Link href="/ethics" target="_blank" rel="noopener">Ethics Policy</Link>,{" "}
                <Link href="/privacy" target="_blank" rel="noopener">Privacy Policy</Link>, and{" "}
                <Link href="/terms" target="_blank" rel="noopener">Terms &amp; Conditions</Link>.
              </span>
            </label>
            <button type="submit" className="btn btn-primary btn-lg full-button" disabled={submitting}>
              {submitting ? "Accepting Invite..." : "Accept Invite"}
            </button>
          </form>
          <p className="auth-footnote">Already have access? <Link href="/login">Sign In</Link></p>
        </>
      ) : null}
    </PublicAuthShell>
  );
}
