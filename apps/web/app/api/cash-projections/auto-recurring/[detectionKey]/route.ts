import { cashProjectionAutoRecurringInputSchema } from "@clearpath/validation";
import { NextResponse } from "next/server";

import { mapCashProjection } from "@/lib/cash-projection";
import { apiErrorMessage, clearPathApiClient, forwardedSessionHeaders } from "@/lib/server-api";

export const runtime = "nodejs";
type Context = { params: Promise<{ detectionKey: string }> };

export async function POST(request: Request, context: Context) {
  const detectionKey = (await context.params).detectionKey.trim();
  if (!detectionKey) return NextResponse.json({ message: "Recurring schedule not found." }, { status: 404 });
  const parsed = cashProjectionAutoRecurringInputSchema.safeParse(await request.json().catch(() => null));
  if (!parsed.success) return NextResponse.json({ message: parsed.error.issues[0]?.message ?? "Check the recurring schedule details." }, { status: 422 });
  try {
    const { data, error, response } = await clearPathApiClient().POST("/v1/cash-projections/auto-recurring/{detection_key}", {
      params: { path: { detection_key: detectionKey } },
      body: {
        action: parsed.data.action,
        month: parsed.data.month ?? null,
        horizon: parsed.data.horizon ?? null,
        view: parsed.data.view,
        start_date: parsed.data.startDate ?? null,
        end_date: parsed.data.endDate ?? null,
        name: parsed.data.name ?? null,
        amount: parsed.data.amount ?? null,
        frequency: parsed.data.frequency ?? null,
        schedule_start_date: parsed.data.scheduleStartDate ?? null,
        second_date: parsed.data.secondDate ?? null,
        recurring_days_of_week: parsed.data.recurringDaysOfWeek,
        recurring_monthly_week_numbers: parsed.data.recurringMonthlyWeekNumbers,
        recurring_monthly_weekday: parsed.data.recurringMonthlyWeekday ?? null,
        category_label: parsed.data.categoryLabel ?? null,
        notes: parsed.data.notes ?? null,
      },
      headers: forwardedSessionHeaders(request),
    });
    if (!response.ok || !data) return NextResponse.json({ message: apiErrorMessage(error, "We could not update that recurring projection.") }, { status: response.status });
    const mapped = mapCashProjection(data);
    if (!mapped.success) return NextResponse.json({ message: "Updated cash projection data did not match the expected contract." }, { status: 502 });
    return NextResponse.json(mapped.data);
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}
