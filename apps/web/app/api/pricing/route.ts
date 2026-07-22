import { NextResponse } from "next/server";

import { mapPricing } from "@/lib/billing";
import { apiErrorMessage, clearPathApiClient, forwardedSessionHeaders } from "@/lib/server-api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const headers = forwardedSessionHeaders(request);
  const client = clearPathApiClient();
  try {
    const [plans, me] = await Promise.all([
      client.GET("/v1/billing/plans", { headers }),
      client.GET("/v1/me", { headers }),
    ]);
    if (!plans.response.ok || !plans.data) {
      return NextResponse.json(
        { message: apiErrorMessage(plans.error, "We could not load billing plans.") },
        { status: plans.response.status },
      );
    }

    const mapped = mapPricing(plans.data, me.response.ok ? (me.data ?? null) : null);
    if (!mapped.success) {
      return NextResponse.json({ message: "Pricing data did not match the expected contract." }, { status: 502 });
    }
    return NextResponse.json(mapped.data, { headers: { "cache-control": "no-store" } });
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}
