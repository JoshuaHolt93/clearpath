import { billingPlanSelectionInputSchema } from "@clearpath/validation";
import { NextResponse } from "next/server";

import { apiErrorMessage, clearPathApiClient, forwardedSessionHeaders } from "@/lib/server-api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const parsed = billingPlanSelectionInputSchema.safeParse(await request.json().catch(() => null));
  if (!parsed.success) return NextResponse.json({ message: parsed.error.issues[0]?.message ?? "Choose a plan." }, { status: 422 });
  try {
    const { data, error, response } = await clearPathApiClient().POST("/v1/billing/plan-selection", {
      headers: forwardedSessionHeaders(request),
      body: {
        plan: parsed.data.plan,
        promotion_code: parsed.data.promotionCode ?? null,
        success_path: "/settings",
        cancel_path: "/billing",
      },
    });
    if (!response.ok || !data) return NextResponse.json({ message: apiErrorMessage(error, "We could not update your plan.") }, { status: response.status });
    return NextResponse.json({
      selectedPlan: data.selected_plan,
      planName: data.plan_name,
      alreadySelected: data.already_selected,
      checkoutUrl: data.checkout_url ?? null,
    });
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}
