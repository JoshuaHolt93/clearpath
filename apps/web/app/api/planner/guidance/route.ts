import { NextResponse } from "next/server";

import { mapPlannerGuidance } from "@/lib/planner";
import { apiErrorMessage, clearPathApiClient, forwardedSessionHeaders } from "@/lib/server-api";

export const runtime = "nodejs";

export async function POST(request: Request) {
  try {
    const { data, error, response } = await clearPathApiClient().POST("/v1/planner/guidance/generate", { body: {}, headers: forwardedSessionHeaders(request) });
    if (!response.ok || !data) return NextResponse.json({ message: apiErrorMessage(error, "We could not generate AI guidance.") }, { status: response.status });
    const mapped = mapPlannerGuidance(data);
    if (!mapped.success) return NextResponse.json({ message: "Planner data did not match the expected contract." }, { status: 502 });
    return NextResponse.json(mapped.data);
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}
