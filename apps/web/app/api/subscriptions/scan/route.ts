import { NextResponse } from "next/server";

import { apiErrorMessage, clearPathApiClient, forwardedSessionHeaders } from "@/lib/server-api";

export async function POST(request: Request) {
  try {
    const { data, error, response } = await clearPathApiClient().POST("/v1/subscriptions/scan", { headers: forwardedSessionHeaders(request) });
    if (!response.ok || !data) return NextResponse.json({ message: apiErrorMessage(error, "We could not scan subscriptions.") }, { status: response.status });
    return NextResponse.json({ syncedCount: data.synced_count });
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}
