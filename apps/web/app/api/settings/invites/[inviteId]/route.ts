import { NextResponse } from "next/server";

import { mapInvite } from "@/lib/settings";
import { apiErrorMessage, clearPathApiClient, forwardedSessionHeaders } from "@/lib/server-api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function DELETE(request: Request, context: { params: Promise<{ inviteId: string }> }) {
  const { inviteId } = await context.params;
  const parsedId = Number(inviteId);
  if (!Number.isInteger(parsedId) || parsedId <= 0) return NextResponse.json({ message: "Invite not found." }, { status: 404 });
  try {
    const { data, error, response } = await clearPathApiClient().DELETE("/v1/households/current/invites/{invite_id}", {
      headers: forwardedSessionHeaders(request),
      params: { path: { invite_id: parsedId } },
      body: { confirm: true },
    });
    if (!response.ok || !data) return NextResponse.json({ message: apiErrorMessage(error, "We could not revoke that invite.") }, { status: response.status });
    return NextResponse.json(mapInvite(data));
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}
