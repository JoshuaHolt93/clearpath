import { NextResponse } from "next/server";

import { mapBilling } from "@/lib/billing";
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
    if (!plans.response.ok || !plans.data) return NextResponse.json({ message: apiErrorMessage(plans.error, "We could not load billing plans.") }, { status: plans.response.status });
    if (!me.response.ok || !me.data) return NextResponse.json({ message: apiErrorMessage(me.error, "We could not load your session.") }, { status: me.response.status });

    // Primary-holder-only billing state and cancellation feedback options.
    let userState = null;
    let feedbackOptions = null;
    if (me.data.primary_account_holder) {
      const [state, options] = await Promise.all([
        client.GET("/v1/billing/status", { headers }),
        client.GET("/v1/feedback/options", { headers }),
      ]);
      userState = state.response.ok ? (state.data ?? null) : null;
      feedbackOptions = options.response.ok ? (options.data ?? null) : null;
    }

    const mapped = mapBilling(plans.data, me.data, userState, feedbackOptions);
    if (!mapped.success) return NextResponse.json({ message: "Billing data did not match the expected contract." }, { status: 502 });
    return NextResponse.json(mapped.data, { headers: { "cache-control": "no-store" } });
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}
