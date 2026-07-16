import type { Metadata } from "next";

import { PendingAuthShell } from "../pending-auth-shell";
import { MfaVerifyPanel } from "./mfa-verify-panel";

export const metadata: Metadata = {
  title: "Verify MFA - ClearPath Finance",
};

export default function MfaVerifyPage() {
  return (
    <PendingAuthShell
      title="Verify Multi-Factor Authentication"
      subtitle="Enter your verification code to continue."
      panelTitle="Authentication Code"
    >
      <MfaVerifyPanel />
    </PendingAuthShell>
  );
}
