import { fixedExpenseInputSchema } from "@clearpath/validation";
import { NextResponse } from "next/server";

import { apiErrorMessage, clearPathApiClient, forwardedSessionHeaders } from "@/lib/server-api";

export const runtime = "nodejs";

export async function POST(request: Request) {
  const parsed = fixedExpenseInputSchema.safeParse(await request.json().catch(() => null));
  if (!parsed.success) return NextResponse.json({ message: parsed.error.issues[0]?.message ?? "Check the fixed expense details." }, { status: 422 });
  const value = parsed.data;
  try {
    const { data, error, response } = await clearPathApiClient().POST("/v1/fixed-expenses", {
      body: {
        name: value.name, amount: value.amount, frequency: value.frequency, start_date: value.startDate,
        second_date: value.secondDate, days_of_week: value.daysOfWeek,
        recurring_monthly_week_numbers: value.recurringMonthlyWeekNumbers,
        recurring_monthly_weekday: value.recurringMonthlyWeekday, category_label: value.categoryLabel,
        entry_context: value.entryContext, notes: value.notes,
      },
      headers: forwardedSessionHeaders(request),
    });
    if (!response.ok || !data) return NextResponse.json({ message: apiErrorMessage(error, "We could not add that fixed expense.") }, { status: response.status });
    return NextResponse.json({ itemId: data.id, name: data.name, monthlyAmount: data.monthly_amount ?? null }, { status: 201 });
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}
