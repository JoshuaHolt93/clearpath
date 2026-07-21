import { NextResponse } from "next/server";

import { apiErrorMessage, clearPathApiClient, forwardedSessionHeaders } from "@/lib/server-api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  try {
    const { data, error, response } = await clearPathApiClient().POST("/v1/billing/portal-sessions", {
      headers: forwardedSessionHeaders(request),
      body: { confirm: true },
    });
    if (!response.ok || !data) return NextResponse.json({ message: apiErrorMessage(error, "We could not open the billing portal.") }, { status: response.status });
    return NextResponse.json({ portalUrl: data.portal_url });
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}
