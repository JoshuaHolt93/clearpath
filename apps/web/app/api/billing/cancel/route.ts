import { billingCancellationInputSchema } from "@clearpath/validation";
import { NextResponse } from "next/server";

import { apiErrorMessage, clearPathApiClient, forwardedSessionHeaders } from "@/lib/server-api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const parsed = billingCancellationInputSchema.safeParse(await request.json().catch(() => null));
  if (!parsed.success) return NextResponse.json({ message: "Check the cancellation details." }, { status: 422 });
  try {
    const { data, error, response } = await clearPathApiClient().POST("/v1/billing/cancellation-sessions", {
      headers: forwardedSessionHeaders(request),
      body: {
        reason: parsed.data.reason ?? null,
        feature_expectation_reason: parsed.data.featureExpectationReason ?? null,
        broken_features: parsed.data.brokenFeatures ?? [],
        description: parsed.data.description ?? null,
        notify_when_addressed: parsed.data.notifyWhenAddressed ?? false,
      },
    });
    if (!response.ok || !data) return NextResponse.json({ message: apiErrorMessage(error, "We could not start cancellation.") }, { status: response.status });
    return NextResponse.json({
      feedbackSaved: data.feedback_saved,
      portalUrl: data.portal_url ?? null,
      message: data.message ?? null,
    });
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}
