import type { Metadata } from "next";

import { PendingAuthShell } from "../pending-auth-shell";
import { MfaRecoveryPanel } from "./mfa-recovery-panel";

export const metadata: Metadata = {
  title: "Use Recovery Code - ClearPath Finance",
};

export default function MfaRecoveryPage() {
  return (
    <PendingAuthShell
      title="Use A Recovery Code"
      subtitle="Enter one unused recovery code to regain access."
      panelTitle="Recovery Code"
    >
      <MfaRecoveryPanel />
    </PendingAuthShell>
  );
}
