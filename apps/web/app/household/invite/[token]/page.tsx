import type { Metadata } from "next";

import { InviteAcceptancePanel } from "./invite-acceptance-panel";

export const metadata: Metadata = { title: "Accept Household Invite - ClearPath Finance" };

export default async function HouseholdInvitePage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  return <InviteAcceptancePanel token={token} />;
}
