import { plaidRefreshSummarySchema } from "@clearpath/validation";
import { NextResponse } from "next/server";

import { apiErrorMessage, clearPathApiClient, forwardedSessionHeaders } from "@/lib/server-api";

export async function POST(request: Request) {
  try {
    const { data, error, response } = await clearPathApiClient().POST("/v1/plaid-items/refresh-stale", {
      body: {},
      headers: forwardedSessionHeaders(request),
    });
    if (!response.ok || !data) {
      return NextResponse.json(
        { message: apiErrorMessage(error, "Live bank refresh could not complete.") },
        { status: response.status },
      );
    }
    const parsed = plaidRefreshSummarySchema.safeParse(data);
    if (!parsed.success) {
      return NextResponse.json({ message: "ClearPath returned invalid refresh details." }, { status: 502 });
    }
    return NextResponse.json(parsed.data, { headers: { "cache-control": "no-store" } });
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}
