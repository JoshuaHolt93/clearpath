import { householdMemberRoleInputSchema } from "@clearpath/validation";
import { NextResponse } from "next/server";

import { mapMember } from "@/lib/settings";
import { apiErrorMessage, clearPathApiClient, forwardedSessionHeaders } from "@/lib/server-api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function parseMemberId(raw: string): number | null {
  const parsed = Number(raw);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null;
}

export async function PATCH(request: Request, context: { params: Promise<{ memberId: string }> }) {
  const { memberId } = await context.params;
  const parsedId = parseMemberId(memberId);
  if (!parsedId) return NextResponse.json({ message: "Household member not found." }, { status: 404 });
  const parsed = householdMemberRoleInputSchema.safeParse(await request.json().catch(() => null));
  if (!parsed.success) return NextResponse.json({ message: "Choose a shared access role." }, { status: 422 });
  try {
    const { data, error, response } = await clearPathApiClient().PATCH("/v1/households/current/members/{member_id}", {
      headers: forwardedSessionHeaders(request),
      params: { path: { member_id: parsedId } },
      body: { member_role: parsed.data.memberRole },
    });
    if (!response.ok || !data) return NextResponse.json({ message: apiErrorMessage(error, "We could not update that member.") }, { status: response.status });
    return NextResponse.json(mapMember(data));
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}

export async function DELETE(request: Request, context: { params: Promise<{ memberId: string }> }) {
  const { memberId } = await context.params;
  const parsedId = parseMemberId(memberId);
  if (!parsedId) return NextResponse.json({ message: "Household member not found." }, { status: 404 });
  try {
    const { data, error, response } = await clearPathApiClient().DELETE("/v1/households/current/members/{member_id}", {
      headers: forwardedSessionHeaders(request),
      params: { path: { member_id: parsedId } },
      body: { confirm: true },
    });
    if (!response.ok || !data) return NextResponse.json({ message: apiErrorMessage(error, "We could not revoke that member.") }, { status: response.status });
    return NextResponse.json(mapMember(data));
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}
