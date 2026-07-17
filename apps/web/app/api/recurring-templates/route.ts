import { recurringTemplateInputSchema } from "@clearpath/validation";
import { NextResponse } from "next/server";

import { apiErrorMessage, clearPathApiClient, forwardedSessionHeaders } from "@/lib/server-api";

export const runtime = "nodejs";

export async function POST(request: Request) {
  const parsed = recurringTemplateInputSchema.safeParse(await request.json().catch(() => null));
  if (!parsed.success) return NextResponse.json({ message: parsed.error.issues[0]?.message ?? "Check the recurring item details." }, { status: 422 });
  const value = parsed.data;
  try {
    const { data, error, response } = await clearPathApiClient().POST("/v1/recurring-templates", {
      body: {
        name: value.name, amount: value.amount, item_type: value.itemType, frequency: value.frequency,
        start_date: value.startDate, second_date: value.secondDate, recurring_days_of_week: value.recurringDaysOfWeek,
        recurring_monthly_week_numbers: value.recurringMonthlyWeekNumbers,
        recurring_monthly_weekday: value.recurringMonthlyWeekday, category_label: value.categoryLabel,
        notes: value.notes, income_adjustment: value.incomeAdjustment,
        income_basis: "take_home", income_type: "salary", paycheck_cadence: "monthly",
        additional_income_frequency: "annual", tax_filing_status: "married_joint", include_payroll_taxes: false,
      },
      headers: forwardedSessionHeaders(request),
    });
    if (!response.ok || !data) return NextResponse.json({ message: apiErrorMessage(error, "We could not add that recurring item.") }, { status: response.status });
    return NextResponse.json({ templateId: data.id, name: data.name, monthlyAmount: data.monthly_amount ?? null }, { status: 201 });
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}
