import { helpViewSchema } from "@clearpath/validation";
import { NextResponse } from "next/server";

import { mapSession } from "@/lib/billing";
import { apiErrorMessage, clearPathApiClient, forwardedSessionHeaders } from "@/lib/server-api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const headers = forwardedSessionHeaders(request);
  const client = clearPathApiClient();
  try {
    const [me, onboarding] = await Promise.all([
      client.GET("/v1/me", { headers }),
      client.GET("/v1/onboarding/status", { params: { query: { step: "" } }, headers }),
    ]);
    if (!me.response.ok || !me.data) {
      return NextResponse.json(
        { message: apiErrorMessage(me.error, "Sign in to open Help.") },
        { status: me.response.status },
      );
    }
    if (!onboarding.response.ok || !onboarding.data) {
      return NextResponse.json(
        { message: apiErrorMessage(onboarding.error, "We could not confirm your setup progress.") },
        { status: onboarding.response.status },
      );
    }
    // Flask ensure_onboarded() requires an income baseline. The broader
    // setup_complete flag also requires Plaid and would block manual households.
    if (!onboarding.data.income_ready) {
      return NextResponse.json({ message: "Finish setup before opening Help." }, { status: 403 });
    }

    const mapped = helpViewSchema.safeParse({ session: mapSession(me.data) });
    if (!mapped.success) {
      return NextResponse.json({ message: "Help data did not match the expected contract." }, { status: 502 });
    }
    return NextResponse.json(mapped.data, { headers: { "cache-control": "no-store" } });
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}
