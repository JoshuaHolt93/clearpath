import { loanPlanScenarioInputSchema } from "@clearpath/validation";
import { NextResponse } from "next/server";

import { mapLoanResource } from "@/lib/loan-plans";
import { apiErrorMessage, clearPathApiClient, forwardedSessionHeaders } from "@/lib/server-api";

export const runtime = "nodejs";
type Context = { params: Promise<{ itemId: string }> };

export async function PATCH(request: Request, context: Context) {
  const { itemId } = await context.params;
  const parsed = loanPlanScenarioInputSchema.safeParse(await request.json().catch(() => null));
  if (!parsed.success) return NextResponse.json({ message: parsed.error.issues[0]?.message ?? "Choose a payoff plan." }, { status: 422 });
  try {
    const { data, error, response } = await clearPathApiClient().PATCH("/v1/loan-plans/{fixed_expense_item_id}/selected-scenario", { params: { path: { fixed_expense_item_id: Number(itemId) } }, body: { selected_scenario: parsed.data.selectedScenario }, headers: forwardedSessionHeaders(request) });
    if (!response.ok || !data) return NextResponse.json({ message: apiErrorMessage(error, "We could not select that payoff plan.") }, { status: response.status });
    const mapped = mapLoanResource(data);
    if (!mapped.success) return NextResponse.json({ message: "Loan plan data did not match the expected contract." }, { status: 502 });
    return NextResponse.json(mapped.data);
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}
