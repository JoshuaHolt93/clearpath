import { subscriptionUpdateInputSchema } from "@clearpath/validation";
import { NextResponse } from "next/server";

import { apiErrorMessage, clearPathApiClient, forwardedSessionHeaders } from "@/lib/server-api";

type Context = { params: Promise<{ subscriptionId: string }> };

export async function PATCH(request: Request, context: Context) {
  const subscriptionId = Number((await context.params).subscriptionId);
  if (!Number.isInteger(subscriptionId) || subscriptionId < 1) return NextResponse.json({ message: "Subscription not found." }, { status: 404 });
  const parsed = subscriptionUpdateInputSchema.safeParse(await request.json().catch(() => null));
  if (!parsed.success) return NextResponse.json({ message: parsed.error.issues[0]?.message ?? "Check the subscription change." }, { status: 422 });
  const value = parsed.data;
  try {
    const { data, error, response } = await clearPathApiClient().PATCH("/v1/subscriptions/{subscription_id}", {
      params: { path: { subscription_id: subscriptionId } },
      body: { status: value.status, notes: value.notes, cycle: value.cycle, cancel_url: value.cancelUrl },
      headers: forwardedSessionHeaders(request),
    });
    if (!response.ok || !data) return NextResponse.json({ message: apiErrorMessage(error, "We could not update that subscription.") }, { status: response.status });
    return NextResponse.json({ subscriptionId: data.id, status: data.status });
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}
