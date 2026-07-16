import type { Metadata } from "next";

import { PendingAuthShell } from "../../pending-auth-shell";
import { PushCallbackPanel } from "./push-callback-panel";

export const metadata: Metadata = {
  title: "Complete Push Approval - ClearPath Finance",
};

export default function MfaPushCallbackPage() {
  return (
    <PendingAuthShell
      title="Completing Push Approval"
      subtitle="ClearPath is confirming the approval from Duo."
      panelTitle="Push Approval"
    >
      <PushCallbackPanel />
    </PendingAuthShell>
  );
}
