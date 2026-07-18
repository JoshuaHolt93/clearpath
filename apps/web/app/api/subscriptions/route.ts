import { subscriptionCreateInputSchema } from "@clearpath/validation";
import { NextResponse } from "next/server";

import { apiErrorMessage, clearPathApiClient, forwardedSessionHeaders } from "@/lib/server-api";
import { mapSubscriptions } from "@/lib/subscriptions";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const headers = forwardedSessionHeaders(request);
  try {
    const [subscriptions, me] = await Promise.all([
      clearPathApiClient().GET("/v1/subscriptions", { headers }),
      clearPathApiClient().GET("/v1/me", { headers }),
    ]);
    if (!subscriptions.response.ok || !subscriptions.data) return NextResponse.json({ message: apiErrorMessage(subscriptions.error, "We could not load subscriptions.") }, { status: subscriptions.response.status });
    if (!me.response.ok || !me.data) return NextResponse.json({ message: apiErrorMessage(me.error, "We could not load your session.") }, { status: me.response.status });
    const mapped = mapSubscriptions(subscriptions.data, me.data);
    if (!mapped.success) return NextResponse.json({ message: "Subscription data did not match the expected contract." }, { status: 502 });
    return NextResponse.json(mapped.data, { headers: { "cache-control": "no-store" } });
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}

export async function POST(request: Request) {
  const parsed = subscriptionCreateInputSchema.safeParse(await request.json().catch(() => null));
  if (!parsed.success) return NextResponse.json({ message: parsed.error.issues[0]?.message ?? "Check the subscription details." }, { status: 422 });
  try {
    const value = parsed.data;
    const { data, error, response } = await clearPathApiClient().POST("/v1/subscriptions", {
      body: { name: value.name, amount: value.amount, cycle: value.cycle, next_charge_date: value.nextChargeDate, notes: value.notes },
      headers: forwardedSessionHeaders(request),
    });
    if (!response.ok || !data) return NextResponse.json({ message: apiErrorMessage(error, "We could not add that subscription.") }, { status: response.status });
    return NextResponse.json({ subscriptionId: data.id }, { status: 201 });
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}
