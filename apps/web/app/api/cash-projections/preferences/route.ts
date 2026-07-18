import { cashProjectionPreferenceInputSchema } from "@clearpath/validation";
import { NextResponse } from "next/server";

import { apiErrorMessage, clearPathApiClient, forwardedSessionHeaders } from "@/lib/server-api";

export const runtime = "nodejs";

export async function PATCH(request: Request) {
  const parsed = cashProjectionPreferenceInputSchema.safeParse(await request.json().catch(() => null));
  if (!parsed.success) return NextResponse.json({ message: parsed.error.issues[0]?.message ?? "Choose a saved time horizon." }, { status: 422 });
  try {
    const { data, error, response } = await clearPathApiClient().PATCH("/v1/cash-projections/preferences", {
      body: { default_horizon: parsed.data.defaultHorizon },
      headers: forwardedSessionHeaders(request),
    });
    if (!response.ok || !data) return NextResponse.json({ message: apiErrorMessage(error, "We could not save that time horizon.") }, { status: response.status });
    return NextResponse.json({ defaultHorizon: data.default_horizon });
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}
