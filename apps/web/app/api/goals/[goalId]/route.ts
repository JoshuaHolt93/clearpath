import { NextResponse } from "next/server";

import { apiErrorMessage, clearPathApiClient, forwardedSessionHeaders } from "@/lib/server-api";

type RouteContext = { params: Promise<{ goalId: string }> };

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
