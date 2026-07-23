"use client";

import {
  mfaEmailCodeResultSchema,
  mfaSetupConfirmRequestSchema,
  mfaSetupResultSchema,
  mfaSetupSchema,
  type MfaSetup,
  type MfaSetupConfirmRequest,
} from "@clearpath/validation";
import Image from "next/image";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import QRCode from "qrcode";
import { type FormEvent, useEffect, useState } from "react";

import { AUTH_NEXT_STEP_PATHS } from "@/lib/auth-navigation";
import { safeLocalReturnUrl } from "@/lib/safe-return-url";

function messageFrom(payload: unknown, fallback: string): string {
  if (payload && typeof payload === "object" && "message" in payload) {
    const message = (payload as { message?: unknown }).message;
    if (typeof message === "string" && message.trim()) {
      return message;
    }
  }
  return fallback;
}

export function MfaSetupPanel() {
  const router = useRouter();
  const searchParams = useSearchParams();
  // When enrolment is launched from Settings it passes ?next=/settings so the
  // user lands back where they started rather than at onboarding/dashboard.
  const nextOverride = safeLocalReturnUrl(searchParams.get("next"));
  const [setup, setSetup] = useState<MfaSetup | null>(null);
  const [qrDataUrl, setQrDataUrl] = useState<string | null>(null);
  const [mobileSetupUrl, setMobileSetupUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [sendingEmail, setSendingEmail] = useState(false);
  const [emailCodeSent, setEmailCodeSent] = useState(false);
  const [recoveryCodes, setRecoveryCodes] = useState<string[] | null>(null);
  const [nextPath, setNextPath] = useState<string>("/onboarding");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    async function loadSetup() {
      try {
        const response = await fetch("/api/auth/mfa/setup", { cache: "no-store" });
        const payload: unknown = await response.json();
        if (!response.ok) {
          throw new Error(messageFrom(payload, "Your pending MFA setup session is unavailable."));
        }
        const parsed = mfaSetupSchema.safeParse(payload);
        if (!parsed.success) {
          throw new Error("ClearPath returned unexpected MFA setup data.");
        }
        if (!active) {
          return;
        }
        setSetup(parsed.data);
        const handoffUrl = `${window.location.origin}/mfa/setup/mobile/${encodeURIComponent(parsed.data.mobileSetupToken)}`;
        setMobileSetupUrl(handoffUrl);
        const qr = await QRCode.toDataURL(handoffUrl, {
          errorCorrectionLevel: "M",
          margin: 1,
          width: 220,
          color: { dark: "#111827", light: "#ffffff" },
        });
        if (active) {
          setQrDataUrl(qr);
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
    void loadSetup();
    return () => {
      active = false;
    };
  }, []);

  async function completeSetup(requestPayload: MfaSetupConfirmRequest) {
    setSubmitting(true);
    setError(null);
    setNotice(null);
    try {
      const response = await fetch("/api/auth/mfa/setup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(requestPayload),
      });
      const payload: unknown = await response.json();
      if (!response.ok) {
        setError(messageFrom(payload, "MFA setup could not be completed."));
        return;
      }
      const result = mfaSetupResultSchema.safeParse(payload);
      if (!result.success) {
        setError("ClearPath returned an unexpected setup result.");
        return;
      }
      const destination = nextOverride || AUTH_NEXT_STEP_PATHS[result.data.nextStep];
      if (result.data.recoveryCodes?.length) {
        setRecoveryCodes(result.data.recoveryCodes);
        setNextPath(destination);
        return;
      }
      router.push(destination);
      router.refresh();
    } catch {
      setError("ClearPath is temporarily unavailable. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleTotpSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    const parsed = mfaSetupConfirmRequestSchema.safeParse({
      action: "verify_totp",
      code: formData.get("code"),
      mfa_push_opt_in: formData.get("mfa_push_opt_in") === "on",
    });
    if (!parsed.success) {
      setError(parsed.error.issues[0]?.message ?? "Check your authentication code.");
      return;
    }
    await completeSetup(parsed.data);
  }

  async function sendEmailCode() {
    setSendingEmail(true);
    setError(null);
    setNotice(null);
    try {
      const response = await fetch("/api/auth/mfa/setup/email-code", { method: "POST" });
      const payload: unknown = await response.json();
      if (!response.ok) {
        setError(messageFrom(payload, "An email verification code could not be sent."));
        return;
      }
      const result = mfaEmailCodeResultSchema.safeParse(payload);
      if (!result.success || !result.data.sent) {
        setError("Email code could not be sent right now. Use another MFA method or try again.");
        return;
      }
      setEmailCodeSent(true);
      setNotice(`A verification code was sent to ${setup?.email ?? "your email"}.`);
    } catch {
      setError("ClearPath is temporarily unavailable. Please try again.");
    } finally {
      setSendingEmail(false);
    }
  }

  async function handleEmailSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    const parsed = mfaSetupConfirmRequestSchema.safeParse({
      action: "confirm_email_code",
      email_code: formData.get("email_code"),
      mfa_push_opt_in: false,
    });
    if (!parsed.success) {
      setError(parsed.error.issues[0]?.message ?? "Check your email verification code.");
      return;
    }
    await completeSetup(parsed.data);
  }

  if (loading) {
    return <p className="pending-status" role="status">Preparing secure MFA setup...</p>;
  }

  if (!setup) {
    return (
      <>
        <div className="alert alert-error" role="alert">{error}</div>
        <p className="panel-footnote"><Link href="/login">Return To Sign In</Link></p>
      </>
    );
  }

  if (recoveryCodes) {
    return (
      <div className="recovery-reveal" aria-live="polite">
        <h3>Recovery Codes</h3>
        <p className="panel-intro">
          Save these codes now. Each can be used once, and ClearPath will not show them again.
        </p>
        <div className="recovery-code-grid">
          {recoveryCodes.map((code) => <code key={code}>{code}</code>)}
        </div>
        <button
          type="button"
          className="btn btn-primary"
          onClick={() => {
            router.push(nextPath);
            router.refresh();
          }}
        >
          Continue
        </button>
      </div>
    );
  }

  return (
    <>
      {error ? <div className="alert alert-error" role="alert">{error}</div> : null}
      {notice ? <div className="alert alert-info" role="status">{notice}</div> : null}

      <p className="panel-intro">
        Scan this QR code with your phone camera. It opens a secure ClearPath setup page and hands off to your authenticator app.
      </p>
      {qrDataUrl ? (
        <div className="mfa-qr-box">
          <Image
            src={qrDataUrl}
            alt="Scan to open the ClearPath authenticator setup page"
            width={220}
            height={220}
            unoptimized
            className="mfa-qr-img"
          />
        </div>
      ) : <p className="pending-status" role="status">Generating setup QR code...</p>}
      <p className="setup-expiry-note">This QR code expires after a short time. Keep this page private.</p>

      <details className="mfa-manual-key">
        <summary>On this device or need manual setup?</summary>
        <div className="mfa-app-actions">
          {mobileSetupUrl ? <a href={mobileSetupUrl} target="_blank" rel="noopener noreferrer" className="btn btn-secondary">Open Secure Setup Page</a> : null}
          <a href={setup.provisioningUri} className="btn btn-secondary">Open Authenticator App</a>
          <a href="https://duo.com/product/multi-factor-authentication-mfa/duo-mobile-app" target="_blank" rel="noopener noreferrer" className="btn btn-secondary">Download Duo Mobile</a>
          <a href="https://www.microsoft.com/en-us/security/mobile-authenticator-app" target="_blank" rel="noopener noreferrer" className="btn btn-secondary">Use Microsoft Authenticator</a>
        </div>
        <div className="mfa-secret-box">
          <span>Setup Key</span>
          <code>{setup.setupKey}</code>
        </div>
      </details>

      <form onSubmit={handleTotpSubmit} noValidate className="setup-method-form">
        <div className="form-group">
          <label className="form-label" htmlFor="setup-totp-code">6-Digit Authentication Code</label>
          <input id="setup-totp-code" name="code" className="form-input code-input" inputMode="numeric" autoComplete="one-time-code" disabled={submitting} required />
        </div>
        {setup.pushAvailable ? (
          <label className="checkbox-row setup-checkbox">
            <input type="checkbox" name="mfa_push_opt_in" defaultChecked disabled={submitting} />
            <span>Use Duo Push approval when I sign in, with authenticator codes as a fallback.</span>
          </label>
        ) : null}
        {!setup.pushAvailable && setup.pushProvider === "duo" && !setup.sharedAccessTotpOnly ? (
          <div className="alert alert-info">Duo Push can be offered after Duo credentials are configured.</div>
        ) : null}
        <button type="submit" className="btn btn-primary" disabled={submitting}>
          {submitting ? "Enabling MFA..." : "Enable MFA"}
        </button>
      </form>

      <hr className="setup-divider" />
      <section className="setup-alternative" aria-labelledby="email-mfa-title">
        <h3 id="email-mfa-title">Prefer Email Codes?</h3>
        <p>ClearPath can email a short-lived code to {setup.email}. An authenticator app is still stronger.</p>
        {setup.emailAvailable ? (
          <>
            <button type="button" className="btn btn-secondary" onClick={sendEmailCode} disabled={sendingEmail || submitting}>
              {sendingEmail ? "Sending Code..." : emailCodeSent ? "Send A New Code" : "Send Email Code"}
            </button>
            {emailCodeSent ? (
              <form onSubmit={handleEmailSubmit} noValidate className="email-code-form">
                <div className="form-group">
                  <label className="form-label" htmlFor="setup-email-code">Email Verification Code</label>
                  <input id="setup-email-code" name="email_code" className="form-input code-input" inputMode="numeric" autoComplete="one-time-code" autoFocus disabled={submitting} required />
                </div>
                <button type="submit" className="btn btn-primary" disabled={submitting}>
                  {submitting ? "Enabling MFA..." : "Use Email Codes For MFA"}
                </button>
              </form>
            ) : null}
          </>
        ) : (
          <div className="alert alert-warning">Email code MFA will be available after transactional email is configured.</div>
        )}
      </section>

      <hr className="setup-divider" />
      <section className="setup-alternative" aria-labelledby="skip-mfa-title">
        <h3 id="skip-mfa-title">Set Up Later</h3>
        <p>You can skip MFA for now and turn it on later from Settings. MFA is recommended for sensitive household financial information.</p>
        <button
          type="button"
          className="btn btn-secondary"
          disabled={submitting}
          onClick={() => void completeSetup({ action: "skip", mfa_push_opt_in: false })}
        >
          Skip MFA For Now
        </button>
      </section>
    </>
  );
}
