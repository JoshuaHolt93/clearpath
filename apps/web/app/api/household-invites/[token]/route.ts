import {
  householdInviteAcceptRequestSchema,
  householdInviteAcceptResultSchema,
  householdInviteTokenSchema,
} from "@clearpath/validation";
import { NextResponse } from "next/server";

import { apiErrorMessage, clearPathApiClient, jsonWithSessionCookie } from "@/lib/server-api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type RouteContext = { params: Promise<{ token: string }> };

export async function GET(_request: Request, context: RouteContext) {
  const { token } = await context.params;
  try {
    const { data, error, response } = await clearPathApiClient().GET("/v1/household-invites/{token}", {
      params: { path: { token } },
    });
    if (!response.ok || !data) {
      return NextResponse.json(
        { message: apiErrorMessage(error, "That household invite is expired or has already been used.") },
        { status: response.status },
      );
    }
    const result = householdInviteTokenSchema.safeParse({
      valid: data.valid,
      email: data.email,
      householdName: data.household_name,
      role: data.role,
    });
    if (!result.success) {
      return NextResponse.json({ message: "ClearPath returned invalid invitation details." }, { status: 502 });
    }
    return jsonWithSessionCookie(result.data, response);
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}

export async function POST(request: Request, context: RouteContext) {
  const { token } = await context.params;
  let payload: unknown;
  try {
    payload = await request.json();
  } catch {
    return NextResponse.json({ message: "Complete the invitation form to continue." }, { status: 400 });
  }
  const parsed = householdInviteAcceptRequestSchema.safeParse(payload);
  if (!parsed.success) {
    return NextResponse.json(
      { message: parsed.error.issues[0]?.message ?? "Check your invitation details." },
      { status: 422 },
    );
  }
  try {
    const { data, error, response } = await clearPathApiClient().POST("/v1/household-invites/{token}/accept", {
      params: { path: { token } },
      body: parsed.data,
    });
    if (!response.ok || !data) {
      return NextResponse.json(
        { message: apiErrorMessage(error, "We could not accept this household invite.") },
        { status: response.status },
      );
    }
    const result = householdInviteAcceptResultSchema.safeParse({ nextStep: data.next_step });
    if (!result.success) {
      return NextResponse.json({ message: "ClearPath returned an invalid invitation destination." }, { status: 502 });
    }
    return jsonWithSessionCookie(result.data, response);
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}
