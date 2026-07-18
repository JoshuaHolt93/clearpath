import { NextResponse } from "next/server";

import { mapAnalytics } from "@/lib/analytics";
import { apiErrorMessage, clearPathApiClient, forwardedSessionHeaders } from "@/lib/server-api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const search = new URL(request.url).searchParams;
  const headers = forwardedSessionHeaders(request);
  try {
    const [analytics, me] = await Promise.all([
      clearPathApiClient().GET("/v1/analytics", {
        headers,
        params: {
          query: {
            range: search.get("range") ?? "month",
            end_month: search.get("end_month") ?? "",
            history_range: search.get("history_range") ?? "quarter",
            history_end_month: search.get("history_end_month") ?? "",
          },
        },
      }),
      clearPathApiClient().GET("/v1/me", { headers }),
    ]);
    if (!analytics.response.ok || !analytics.data) return NextResponse.json({ message: apiErrorMessage(analytics.error, "We could not load analytics.") }, { status: analytics.response.status });
    if (!me.response.ok || !me.data) return NextResponse.json({ message: apiErrorMessage(me.error, "We could not load your session.") }, { status: me.response.status });
    const mapped = mapAnalytics(analytics.data, me.data);
    if (!mapped.success) return NextResponse.json({ message: "Analytics data did not match the expected contract." }, { status: 502 });
    return NextResponse.json(mapped.data, { headers: { "cache-control": "no-store" } });
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}
