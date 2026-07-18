import { NextResponse } from "next/server";

import { mapPlannerView } from "@/lib/planner";
import { apiErrorMessage, clearPathApiClient, forwardedSessionHeaders } from "@/lib/server-api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const headers = forwardedSessionHeaders(request);
  try {
    const [guidance, me] = await Promise.all([
      clearPathApiClient().GET("/v1/planner/guidance", { headers }),
      clearPathApiClient().GET("/v1/me", { headers }),
    ]);
    if (!guidance.response.ok || !guidance.data) return NextResponse.json({ message: apiErrorMessage(guidance.error, "We could not load AI Planner.") }, { status: guidance.response.status });
    if (!me.response.ok || !me.data) return NextResponse.json({ message: apiErrorMessage(me.error, "We could not load your session.") }, { status: me.response.status });
    const mapped = mapPlannerView(guidance.data, me.data);
    if (!mapped.success) return NextResponse.json({ message: "Planner data did not match the expected contract." }, { status: 502 });
    return NextResponse.json(mapped.data, { headers: { "cache-control": "no-store" } });
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}
