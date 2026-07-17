import { budgetAmountInputSchema, budgetDeleteInputSchema } from "@clearpath/validation";
import { NextResponse } from "next/server";

import { apiErrorMessage, clearPathApiClient, forwardedSessionHeaders } from "@/lib/server-api";

export const runtime = "nodejs";

type Context = { params: Promise<{ categoryId: string }> };

function categoryIdFrom(value: string): number | null {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null;
}

export async function PATCH(request: Request, context: Context) {
  const categoryId = categoryIdFrom((await context.params).categoryId);
  if (!categoryId) return NextResponse.json({ message: "Budget category not found." }, { status: 404 });
  const parsed = budgetAmountInputSchema.safeParse(await request.json().catch(() => null));
  if (!parsed.success) return NextResponse.json({ message: parsed.error.issues[0]?.message ?? "Check the budget amount." }, { status: 422 });
  try {
    const { data, error, response } = await clearPathApiClient().PATCH("/v1/budgets/{category_id}", {
      params: { path: { category_id: categoryId } },
      body: { monthly_target: parsed.data.monthlyTarget, budget_month: parsed.data.budgetMonth },
      headers: forwardedSessionHeaders(request),
    });
    if (!response.ok || !data) return NextResponse.json({ message: apiErrorMessage(error, "We could not update that budget.") }, { status: response.status });
    return NextResponse.json({ categoryId: data.category.id, monthlyTarget: data.category.monthly_target });
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}

export async function DELETE(request: Request, context: Context) {
  const categoryId = categoryIdFrom((await context.params).categoryId);
  if (!categoryId) return NextResponse.json({ message: "Budget category not found." }, { status: 404 });
  const parsed = budgetDeleteInputSchema.safeParse(await request.json().catch(() => ({})));
  if (!parsed.success) return NextResponse.json({ message: "Check the budget request." }, { status: 422 });
  try {
    const { data, error, response } = await clearPathApiClient().DELETE("/v1/budgets/{category_id}", {
      params: { path: { category_id: categoryId } },
      body: { budget_month: parsed.data.budgetMonth },
      headers: forwardedSessionHeaders(request),
    });
    if (!response.ok || !data) return NextResponse.json({ message: apiErrorMessage(error, "We could not remove that budget.") }, { status: response.status });
    return NextResponse.json({ deletedCategoryId: data.deleted_category_id });
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}
