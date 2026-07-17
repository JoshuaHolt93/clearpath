import { budgetLayoutInputSchema } from "@clearpath/validation";
import { NextResponse } from "next/server";

import { apiErrorMessage, clearPathApiClient, forwardedSessionHeaders } from "@/lib/server-api";

export const runtime = "nodejs";

export async function PATCH(request: Request) {
  const parsed = budgetLayoutInputSchema.safeParse(await request.json().catch(() => null));
  if (!parsed.success) return NextResponse.json({ message: parsed.error.issues[0]?.message ?? "Check the budget layout." }, { status: 422 });
  try {
    const { data, error, response } = await clearPathApiClient().PATCH("/v1/budgets/layout", {
      body: { budget_month: parsed.data.budgetMonth, rows: parsed.data.rows.map((row) => ({ category_id: row.categoryId, group_key: row.groupKey })) },
      headers: forwardedSessionHeaders(request),
    });
    if (!response.ok || !data) return NextResponse.json({ message: apiErrorMessage(error, "We could not save that budget layout.") }, { status: response.status });
    return NextResponse.json({ ok: data.ok, updated: data.updated });
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}
