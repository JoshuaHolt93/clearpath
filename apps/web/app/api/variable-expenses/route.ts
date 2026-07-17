import { variableExpenseInputSchema } from "@clearpath/validation";
import { NextResponse } from "next/server";

import { apiErrorMessage, clearPathApiClient, forwardedSessionHeaders } from "@/lib/server-api";

export const runtime = "nodejs";

export async function POST(request: Request) {
  const parsed = variableExpenseInputSchema.safeParse(await request.json().catch(() => null));
  if (!parsed.success) return NextResponse.json({ message: parsed.error.issues[0]?.message ?? "Check the flexible budget details." }, { status: 422 });
  const value = parsed.data;
  try {
    const { data, error, response } = await clearPathApiClient().POST("/v1/variable-expenses", {
      body: {
        name: value.name, amount: value.amount, frequency: value.frequency,
        use_specific_date: value.useSpecificDate, specific_date: value.specificDate,
        days_of_week: value.daysOfWeek, category_label: value.categoryLabel, notes: value.notes,
      },
      headers: forwardedSessionHeaders(request),
    });
    if (!response.ok || !data) return NextResponse.json({ message: apiErrorMessage(error, "We could not add that flexible budget.") }, { status: response.status });
    return NextResponse.json({ itemId: data.id, name: data.name, monthlyAmount: data.monthly_amount ?? null }, { status: 201 });
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}
