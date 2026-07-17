import { budgetCreateInputSchema } from "@clearpath/validation";
import { NextResponse } from "next/server";

import { apiErrorMessage, clearPathApiClient, forwardedSessionHeaders } from "@/lib/server-api";

export const runtime = "nodejs";

export async function POST(request: Request) {
  const parsed = budgetCreateInputSchema.safeParse(await request.json().catch(() => null));
  if (!parsed.success) return NextResponse.json({ message: parsed.error.issues[0]?.message ?? "Check the budget details." }, { status: 422 });
  try {
    const { data, error, response } = await clearPathApiClient().POST("/v1/budgets", {
      body: { category_label: parsed.data.categoryLabel, monthly_target: parsed.data.monthlyTarget, category_kind: parsed.data.categoryKind, budget_month: parsed.data.budgetMonth },
      headers: forwardedSessionHeaders(request),
    });
    if (!response.ok || !data) return NextResponse.json({ message: apiErrorMessage(error, "We could not add that budget.") }, { status: response.status });
    return NextResponse.json({ categoryId: data.category.id, category: data.category.name, monthlyTarget: data.category.monthly_target }, { status: 201 });
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}
