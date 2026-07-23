import type { Metadata } from "next";
import { Suspense } from "react";

import { PendingAuthShell } from "../pending-auth-shell";
import { MfaSetupPanel } from "./mfa-setup-panel";

export const metadata: Metadata = {
  title: "Set Up MFA - ClearPath Finance",
};

export default function MfaSetupPage() {
  return (
    <PendingAuthShell
      title="Set Up Multi-Factor Authentication"
      subtitle="Protect your financial data with a one-time code from an authenticator app or email."
      panelTitle="Authenticator App Setup"
    >
      {/* MfaSetupPanel reads useSearchParams() (the ?next= return target);
          Next 15 requires a Suspense boundary around it or the static
          prerender of this route fails the build. */}
      <Suspense fallback={<p className="pending-status" role="status">Loading setup...</p>}>
        <MfaSetupPanel />
      </Suspense>
    </PendingAuthShell>
  );
}
