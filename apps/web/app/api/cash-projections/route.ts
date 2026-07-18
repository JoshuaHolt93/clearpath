import { NextResponse } from "next/server";

import { mapCashProjection } from "@/lib/cash-projection";
import { apiErrorMessage, clearPathApiClient, forwardedSessionHeaders } from "@/lib/server-api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const horizons = new Set(["week", "1m", "3m", "6m", "custom"]);
const views = new Set(["calendar", "list", "graph"]);

export async function GET(request: Request) {
  const url = new URL(request.url);
  const rawHorizon = url.searchParams.get("horizon") ?? undefined;
  const rawView = url.searchParams.get("view") ?? "calendar";
  const horizon = rawHorizon && horizons.has(rawHorizon) ? rawHorizon as "week" | "1m" | "3m" | "6m" | "custom" : undefined;
  const view = views.has(rawView) ? rawView as "calendar" | "list" | "graph" : "calendar";
  try {
    const { data, error, response } = await clearPathApiClient().GET("/v1/cash-projections", {
      params: { query: {
        month: url.searchParams.get("month") ?? undefined,
        horizon,
        view,
        start_date: url.searchParams.get("start_date") ?? undefined,
        end_date: url.searchParams.get("end_date") ?? undefined,
      } },
      headers: forwardedSessionHeaders(request),
    });
    if (!response.ok || !data) return NextResponse.json({ message: apiErrorMessage(error, "We could not load cash balance projections.") }, { status: response.status });
    const mapped = mapCashProjection(data);
    if (!mapped.success) return NextResponse.json({ message: "Cash projection data did not match the expected contract." }, { status: 502 });
    return NextResponse.json(mapped.data, { headers: { "cache-control": "no-store" } });
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}
