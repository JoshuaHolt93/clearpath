import { NextResponse } from "next/server";

import { apiErrorMessage, clearPathApiClient, forwardedSessionHeaders } from "@/lib/server-api";

type Context = { params: Promise<{ subscriptionId: string; transactionId: string }> };

export async function POST(request: Request, context: Context) {
  const params = await context.params;
  const subscriptionId = Number(params.subscriptionId);
  const transactionId = Number(params.transactionId);
  if (![subscriptionId, transactionId].every((value) => Number.isInteger(value) && value > 0)) return NextResponse.json({ message: "Subscription evidence not found." }, { status: 404 });
  try {
    const { data, error, response } = await clearPathApiClient().POST("/v1/subscriptions/{subscription_id}/evidence/{transaction_id}/ignore", {
      params: { path: { subscription_id: subscriptionId, transaction_id: transactionId } },
      headers: forwardedSessionHeaders(request),
    });
    if (!response.ok || !data) return NextResponse.json({ message: apiErrorMessage(error, "We could not ignore that transaction.") }, { status: response.status });
    return NextResponse.json({ subscriptionId: data.id, evidenceCount: data.evidence?.length ?? 0 });
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}
