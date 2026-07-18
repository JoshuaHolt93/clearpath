import { plannerPreferenceInputSchema } from "@clearpath/validation";
import { NextResponse } from "next/server";

import { mapPlannerGuidance } from "@/lib/planner";
import { apiErrorMessage, clearPathApiClient, forwardedSessionHeaders } from "@/lib/server-api";

export const runtime = "nodejs";

export async function PATCH(request: Request) {
  const parsed = plannerPreferenceInputSchema.safeParse(await request.json().catch(() => null));
  if (!parsed.success) return NextResponse.json({ message: parsed.error.issues[0]?.message ?? "Choose an AI provider and model." }, { status: 422 });
  try {
    const { data, error, response } = await clearPathApiClient().PATCH("/v1/planner/preferences", { body: parsed.data, headers: forwardedSessionHeaders(request) });
    if (!response.ok || !data) return NextResponse.json({ message: apiErrorMessage(error, "We could not save that AI preference.") }, { status: response.status });
    const mapped = mapPlannerGuidance(data);
    if (!mapped.success) return NextResponse.json({ message: "Planner data did not match the expected contract." }, { status: 502 });
    return NextResponse.json(mapped.data);
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}
