import { cashProjectionCalendarFeedInputSchema } from "@clearpath/validation";
import { NextResponse } from "next/server";

import { mapCashProjectionCalendarFeed } from "@/lib/cash-projection";
import { apiErrorMessage, clearPathApiClient, forwardedSessionHeaders } from "@/lib/server-api";

export const runtime = "nodejs";

export async function PATCH(request: Request) {
  const parsed = cashProjectionCalendarFeedInputSchema.safeParse(await request.json().catch(() => null));
  if (!parsed.success) return NextResponse.json({ message: parsed.error.issues[0]?.message ?? "Choose a calendar action." }, { status: 422 });
  try {
    const { data, error, response } = await clearPathApiClient().PATCH("/v1/cash-projections/calendar-feed", {
      body: parsed.data,
      headers: forwardedSessionHeaders(request),
    });
    if (!response.ok || !data) return NextResponse.json({ message: apiErrorMessage(error, "We could not update calendar sync.") }, { status: response.status });
    return NextResponse.json(mapCashProjectionCalendarFeed(data));
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}
