import { householdInviteInputSchema } from "@clearpath/validation";
import { NextResponse } from "next/server";

import { mapInvite } from "@/lib/settings";
import { apiErrorMessage, clearPathApiClient, forwardedSessionHeaders } from "@/lib/server-api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const parsed = householdInviteInputSchema.safeParse(await request.json().catch(() => null));
  if (!parsed.success) return NextResponse.json({ message: parsed.error.issues[0]?.message ?? "Check the invite details." }, { status: 422 });
  try {
    const { data, error, response } = await clearPathApiClient().POST("/v1/households/current/invites", {
      headers: forwardedSessionHeaders(request),
      body: { invite_email: parsed.data.inviteEmail, invite_role: parsed.data.inviteRole },
    });
    if (!response.ok || !data) return NextResponse.json({ message: apiErrorMessage(error, "We could not create that invite.") }, { status: response.status });
    return NextResponse.json(
      {
        invite: mapInvite(data.invite),
        emailSent: data.email_sent,
        fallbackInviteUrl: data.fallback_invite_url ?? null,
        deliveryReason: data.delivery_reason ?? null,
      },
      { status: 201 },
    );
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}
