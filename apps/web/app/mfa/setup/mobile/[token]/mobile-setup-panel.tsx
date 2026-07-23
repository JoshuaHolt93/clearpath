"use client";

import { mfaMobileSetupSchema } from "@clearpath/validation";
import Link from "next/link";
import { useEffect, useState } from "react";

function messageFrom(payload: unknown, fallback: string): string {
  if (payload && typeof payload === "object" && "message" in payload) {
    const message = (payload as { message?: unknown }).message;
    if (typeof message === "string" && message.trim()) {
      return message;
    }
  }
  return fallback;
}

export function MobileSetupPanel({ token }: Readonly<{ token: string }>) {
  const [provisioningUri, setProvisioningUri] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [expired, setExpired] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    let handoffTimer: number | undefined;
    async function loadSetup() {
      try {
        const response = await fetch(`/api/auth/mfa/setup/mobile/${encodeURIComponent(token)}`, { cache: "no-store" });
        const payload: unknown = await response.json();
        if (!response.ok) {
          if (active) {
            setExpired(response.status === 410);
          }
          throw new Error(messageFrom(payload, "This MFA setup link is expired or invalid."));
        }
        const parsed = mfaMobileSetupSchema.safeParse(payload);
        if (!parsed.success || !parsed.data.provisioningUri) {
          throw new Error("ClearPath returned invalid authenticator setup data.");
        }
        if (active) {
          setProvisioningUri(parsed.data.provisioningUri);
          handoffTimer = window.setTimeout(() => {
            window.location.href = parsed.data.provisioningUri ?? "";
          }, 500);
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
      if (handoffTimer !== undefined) {
        window.clearTimeout(handoffTimer);
      }
    };
  }, [token]);

  if (loading) {
    return <p className="pending-status" role="status">Opening your authenticator app...</p>;
  }

  if (!provisioningUri) {
    return (
      <>
        <div className="alert alert-error" role="alert">{error}</div>
        <p className="panel-intro">
          {expired
            ? "For your security, setup links work only for a short time. Return to MFA setup and scan the QR code again."
            : "Return to the ClearPath MFA setup page and try again."}
        </p>
        <p className="panel-footnote"><Link href="/mfa/setup">Return To MFA Setup</Link></p>
      </>
    );
  }

  return (
    <>
      <p className="panel-intro">Your phone should prompt you to add ClearPath Finance.</p>
      <a href={provisioningUri} className="btn btn-primary full-button">Open Authenticator App</a>
      <p className="panel-footnote">On iPhone this may open the built-in <strong>Passwords</strong> app &mdash; that is expected: choose &ldquo;Set Up Verification Code&rdquo; there, or tap the button again to use a dedicated authenticator app instead. Either way, enter the 6-digit code back on your computer to finish.</p>
      <div className="mfa-app-actions mobile-download-actions">
        <a href="https://duo.com/product/multi-factor-authentication-mfa/duo-mobile-app" target="_blank" rel="noopener noreferrer" className="btn btn-secondary">Download Duo Mobile</a>
        <a href="https://www.microsoft.com/en-us/security/mobile-authenticator-app" target="_blank" rel="noopener noreferrer" className="btn btn-secondary">Use Microsoft Authenticator</a>
      </div>
    </>
  );
}
