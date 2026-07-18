import { goalMutationInputSchema } from "@clearpath/validation";
import { NextResponse } from "next/server";

import { mapGoal } from "@/lib/goals";
import { apiErrorMessage, clearPathApiClient, forwardedSessionHeaders } from "@/lib/server-api";

type RouteContext = { params: Promise<{ goalId: string }> };

export async function PATCH(request: Request, context: RouteContext) {
  const { goalId } = await context.params;
  const parsedId = Number(goalId);
  if (!Number.isInteger(parsedId) || parsedId <= 0) return NextResponse.json({ message: "Goal not found." }, { status: 404 });
  const parsed = goalMutationInputSchema.safeParse(await request.json().catch(() => null));
  if (!parsed.success) return NextResponse.json({ message: parsed.error.issues[0]?.message ?? "Check the goal details." }, { status: 422 });
  try {
    const value = parsed.data;
    const { data, error, response } = await clearPathApiClient().PATCH("/v1/goals/{goal_id}", {
      params: { path: { goal_id: parsedId } },
      body: { name: value.name, goal_type: value.goalType, target_amount: value.targetAmount, current_amount: value.currentAmount, monthly_contribution: value.monthlyContribution, target_date: value.targetDate, fixed_expense_item_id: value.goalType === "debt" ? value.fixedExpenseItemId : null },
      headers: forwardedSessionHeaders(request),
    });
    if (!response.ok || !data) return NextResponse.json({ message: apiErrorMessage(error, "We could not update that goal.") }, { status: response.status });
    return NextResponse.json(mapGoal(data));
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}

export async function DELETE(request: Request, context: RouteContext) {
  const { goalId } = await context.params;
  const parsedId = Number(goalId);
  if (!Number.isInteger(parsedId) || parsedId <= 0) {
    return NextResponse.json({ message: "Goal not found." }, { status: 404 });
  }
  try {
    const { data, error, response } = await clearPathApiClient().DELETE("/v1/goals/{goal_id}", {
      params: { path: { goal_id: parsedId } },
      body: { confirm: true },
      headers: forwardedSessionHeaders(request),
    });
    if (!response.ok || !data) {
      return NextResponse.json(
        { message: apiErrorMessage(error, "We could not delete that goal.") },
        { status: response.status },
      );
    }
    return NextResponse.json({ deletedGoalId: data.deleted_goal_id });
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}
