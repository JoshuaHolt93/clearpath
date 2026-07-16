import type { Metadata } from "next";

import { PendingAuthShell } from "../../../pending-auth-shell";
import { MobileSetupPanel } from "./mobile-setup-panel";

export const metadata: Metadata = {
  title: "Open Authenticator App - ClearPath Finance",
};

export default async function MobileMfaSetupPage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  return (
    <PendingAuthShell
      title="Open Your Authenticator App"
      subtitle="Add ClearPath Finance to your authenticator app."
      panelTitle="Secure Mobile Setup"
    >
      <MobileSetupPanel token={token} />
    </PendingAuthShell>
  );
}
