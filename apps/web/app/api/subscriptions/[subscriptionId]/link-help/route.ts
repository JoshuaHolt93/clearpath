import { NextResponse } from "next/server";

import { apiErrorMessage, clearPathApiClient, forwardedSessionHeaders } from "@/lib/server-api";

type Context = { params: Promise<{ subscriptionId: string }> };

export async function POST(request: Request, context: Context) {
  const subscriptionId = Number((await context.params).subscriptionId);
  if (!Number.isInteger(subscriptionId) || subscriptionId < 1) return NextResponse.json({ message: "Subscription not found." }, { status: 404 });
  try {
    const { data, error, response } = await clearPathApiClient().POST("/v1/subscriptions/{subscription_id}/link-help", {
      params: { path: { subscription_id: subscriptionId } }, body: {}, headers: forwardedSessionHeaders(request),
    });
    if (!response.ok || !data) return NextResponse.json({ message: apiErrorMessage(error, "We could not find a management link.") }, { status: response.status });
    return NextResponse.json(data);
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}
