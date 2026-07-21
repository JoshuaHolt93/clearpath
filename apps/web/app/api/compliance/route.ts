import { NextResponse } from "next/server";

import { mapCompliance } from "@/lib/feedback";
import { apiErrorMessage, clearPathApiClient, forwardedSessionHeaders } from "@/lib/server-api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const headers = forwardedSessionHeaders(request);
  const client = clearPathApiClient();
  try {
    const me = await client.GET("/v1/me", { headers });
    if (!me.response.ok || !me.data) return NextResponse.json({ message: apiErrorMessage(me.error, "We could not load your session.") }, { status: me.response.status });
    // Only admins may read control evaluations; the API returns 403 otherwise.
    let evaluations = null;
    if (me.data.is_admin) {
      const result = await client.GET("/v1/compliance/control-evaluations", { headers });
      evaluations = result.response.ok ? (result.data ?? null) : null;
    }
    const mapped = mapCompliance(me.data, evaluations);
    if (!mapped.success) return NextResponse.json({ message: "Compliance data did not match the expected contract." }, { status: 502 });
    return NextResponse.json(mapped.data, { headers: { "cache-control": "no-store" } });
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}

export async function POST(request: Request) {
  try {
    const { data, error, response } = await clearPathApiClient().POST("/v1/compliance/control-evaluations/run", {
      headers: forwardedSessionHeaders(request),
      body: { confirm: true },
    });
    if (!response.ok || !data) return NextResponse.json({ message: apiErrorMessage(error, "We could not run the control evaluations.") }, { status: response.status });
    return NextResponse.json({ evaluated: data.evaluated, message: `Recorded ${data.evaluated} SOC2 CC4.1 control evaluation results.` });
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}
