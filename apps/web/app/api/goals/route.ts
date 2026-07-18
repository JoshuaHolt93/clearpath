import { goalMutationInputSchema } from "@clearpath/validation";
import { NextResponse } from "next/server";

import { mapGoal, mapGoals } from "@/lib/goals";
import { apiErrorMessage, clearPathApiClient, forwardedSessionHeaders } from "@/lib/server-api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function apiBody(value: ReturnType<typeof goalMutationInputSchema.parse>) {
  return {
    name: value.name,
    goal_type: value.goalType,
    target_amount: value.targetAmount,
    current_amount: value.currentAmount,
    monthly_contribution: value.monthlyContribution,
    target_date: value.targetDate,
    fixed_expense_item_id: value.goalType === "debt" ? value.fixedExpenseItemId : null,
  };
}

export async function GET(request: Request) {
  const headers = forwardedSessionHeaders(request);
  try {
    const [goals, me] = await Promise.all([
      clearPathApiClient().GET("/v1/goals", { headers }),
      clearPathApiClient().GET("/v1/me", { headers }),
    ]);
    if (!goals.response.ok || !goals.data) return NextResponse.json({ message: apiErrorMessage(goals.error, "We could not load goals.") }, { status: goals.response.status });
    if (!me.response.ok || !me.data) return NextResponse.json({ message: apiErrorMessage(me.error, "We could not load your session.") }, { status: me.response.status });
    const mapped = mapGoals(goals.data, me.data);
    if (!mapped.success) return NextResponse.json({ message: "Goal data did not match the expected contract." }, { status: 502 });
    return NextResponse.json(mapped.data, { headers: { "cache-control": "no-store" } });
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}

export async function POST(request: Request) {
  const parsed = goalMutationInputSchema.safeParse(await request.json().catch(() => null));
  if (!parsed.success) return NextResponse.json({ message: parsed.error.issues[0]?.message ?? "Check the goal details." }, { status: 422 });
  try {
    const { data, error, response } = await clearPathApiClient().POST("/v1/goals", { body: apiBody(parsed.data), headers: forwardedSessionHeaders(request) });
    if (!response.ok || !data) return NextResponse.json({ message: apiErrorMessage(error, "We could not create that goal.") }, { status: response.status });
    return NextResponse.json(mapGoal(data), { status: 201 });
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}
