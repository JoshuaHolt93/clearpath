import { plannerPageContextInputSchema } from "@clearpath/validation";
import { NextResponse } from "next/server";

import { mapPlannerPageContext } from "@/lib/planner";
import { apiErrorMessage, clearPathApiClient, forwardedSessionHeaders } from "@/lib/server-api";

export const runtime = "nodejs";

export async function POST(request: Request) {
  const parsed = plannerPageContextInputSchema.safeParse(await request.json().catch(() => null));
  if (!parsed.success) return NextResponse.json({ message: parsed.error.issues[0]?.message ?? "Check the AI Coach request." }, { status: 422 });
  try {
    const { data, error, response } = await clearPathApiClient().POST("/v1/planner/page-context", {
      body: {
        path: parsed.data.path,
        title: parsed.data.title,
        section: parsed.data.section,
        visible_text: parsed.data.visibleText,
        question: parsed.data.question,
      },
      headers: forwardedSessionHeaders(request),
    });
    if (!response.ok || !data) return NextResponse.json({ message: apiErrorMessage(error, "AI Coach could not review this page.") }, { status: response.status });
    const mapped = mapPlannerPageContext(data);
    if (!mapped.success) return NextResponse.json({ message: "AI Coach data did not match the expected contract." }, { status: 502 });
    return NextResponse.json(mapped.data);
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}
