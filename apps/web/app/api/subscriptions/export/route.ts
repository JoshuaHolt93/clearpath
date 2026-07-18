import { NextResponse } from "next/server";

import { apiErrorMessage, clearPathApiClient, forwardedSessionHeaders } from "@/lib/server-api";

export async function GET(request: Request) {
  try {
    const { data, error, response } = await clearPathApiClient().GET("/v1/subscriptions/export.csv", { headers: forwardedSessionHeaders(request) });
    if (!response.ok) return NextResponse.json({ message: apiErrorMessage(error, "We could not export subscriptions.") }, { status: response.status });
    const csv = typeof data === "string" ? data : "";
    return new Response(csv, { status: 200, headers: { "content-type": "text/csv; charset=utf-8", "content-disposition": response.headers.get("content-disposition") ?? "attachment; filename=clearpath-subscriptions.csv", "cache-control": "no-store" } });
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}
