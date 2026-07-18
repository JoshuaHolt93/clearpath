import { transactionCategoryUpdateInputSchema } from "@clearpath/validation";
import { NextResponse } from "next/server";

import { apiErrorMessage, clearPathApiClient, forwardedSessionHeaders } from "@/lib/server-api";

type Context = { params: Promise<{ transactionId: string }> };

export async function PATCH(request: Request, context: Context) {
  const transactionId = Number((await context.params).transactionId);
  if (!Number.isInteger(transactionId) || transactionId < 1) return NextResponse.json({ message: "Transaction not found." }, { status: 404 });
  const parsed = transactionCategoryUpdateInputSchema.safeParse(await request.json().catch(() => null));
  if (!parsed.success) return NextResponse.json({ message: parsed.error.issues[0]?.message ?? "Check the category details." }, { status: 422 });
  const value = parsed.data;
  try {
    const { data, error, response } = await clearPathApiClient().PATCH("/v1/transactions/{transaction_id}/category", {
      params: { path: { transaction_id: transactionId } },
      body: { category_id: value.categoryId, new_category_name: value.newCategoryName, apply_to_similar: value.applyToSimilar,
        mark_recurring: value.markRecurring, recurring_name: value.recurringName, recurring_start_date: value.recurringStartDate,
        recurring_second_date: value.recurringSecondDate, recurring_frequency: value.recurringFrequency,
        recurring_days_of_week: value.recurringDaysOfWeek, recurring_monthly_week_numbers: value.recurringMonthlyWeekNumbers,
        recurring_monthly_weekday: value.recurringMonthlyWeekday },
      headers: forwardedSessionHeaders(request),
    });
    if (!response.ok || !data) return NextResponse.json({ message: apiErrorMessage(error, "We could not update that transaction.") }, { status: response.status });
    return NextResponse.json({ transactionId: data.transaction.id, similarUpdatedCount: data.similar_updated_count, ruleCreated: data.rule_created, recurringMessage: data.recurring_message ?? null });
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}
