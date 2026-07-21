import { feedbackInputSchema } from "@clearpath/validation";
import { NextResponse } from "next/server";

import { mapFeedback } from "@/lib/feedback";
import { apiErrorMessage, clearPathApiClient, forwardedSessionHeaders } from "@/lib/server-api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const headers = forwardedSessionHeaders(request);
  const client = clearPathApiClient();
  try {
    const [options, me] = await Promise.all([
      client.GET("/v1/feedback/options", { headers }),
      client.GET("/v1/me", { headers }),
    ]);
    if (!options.response.ok || !options.data) return NextResponse.json({ message: apiErrorMessage(options.error, "We could not load feedback options.") }, { status: options.response.status });
    if (!me.response.ok || !me.data) return NextResponse.json({ message: apiErrorMessage(me.error, "We could not load your session.") }, { status: me.response.status });
    const mapped = mapFeedback(me.data, options.data);
    if (!mapped.success) return NextResponse.json({ message: "Feedback data did not match the expected contract." }, { status: 502 });
    return NextResponse.json(mapped.data, { headers: { "cache-control": "no-store" } });
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}

export async function POST(request: Request) {
  const parsed = feedbackInputSchema.safeParse(await request.json().catch(() => null));
  if (!parsed.success) return NextResponse.json({ message: parsed.error.issues[0]?.message ?? "Check the feedback details." }, { status: 422 });
  try {
    const { data, error, response } = await clearPathApiClient().POST("/v1/feedback", {
      headers: forwardedSessionHeaders(request),
      body: {
        reason: parsed.data.reason,
        feature_expectation_reason: parsed.data.featureExpectationReason ?? null,
        broken_features: parsed.data.brokenFeatures ?? [],
        description: parsed.data.description ?? null,
        notify_when_addressed: parsed.data.notifyWhenAddressed ?? false,
      },
    });
    if (!response.ok || !data) return NextResponse.json({ message: apiErrorMessage(error, "We could not save your feedback.") }, { status: response.status });
    return NextResponse.json({ saved: true, message: "Thanks for the feedback. It has been saved for product review." }, { status: 201 });
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}
