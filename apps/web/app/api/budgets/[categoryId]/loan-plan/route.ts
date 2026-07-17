import { NextResponse } from "next/server";

import { apiErrorMessage, clearPathApiClient, forwardedSessionHeaders } from "@/lib/server-api";

export const runtime = "nodejs";

export async function POST(request: Request, { params }: { params: Promise<{ categoryId: string }> }) {
  const categoryId = Number((await params).categoryId);
  if (!Number.isInteger(categoryId) || categoryId <= 0) return NextResponse.json({ message: "Budget category not found." }, { status: 404 });
  try {
    const { data, error, response } = await clearPathApiClient().POST("/v1/budgets/{category_id}/loan-plan", {
      params: { path: { category_id: categoryId } },
      headers: forwardedSessionHeaders(request),
    });
    if (!response.ok || !data) return NextResponse.json({ message: apiErrorMessage(error, "We could not open that amortization plan.") }, { status: response.status });
    return NextResponse.json({ fixedExpenseItemId: data.fixed_expense.id });
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}
