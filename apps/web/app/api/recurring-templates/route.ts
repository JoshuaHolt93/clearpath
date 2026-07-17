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
        income_replacement: value.incomeReplacement, income_basis: value.incomeBasis ?? "take_home",
        income_type: value.incomeType ?? "salary", paycheck_cadence: value.paycheckCadence ?? "monthly",
        income_next_pay_date: value.incomeNextPayDate, income_amount: value.incomeAmount,
        hourly_hours_per_week: value.hourlyHoursPerWeek, additional_income_amount: value.additionalIncomeAmount,
        additional_income_frequency: value.additionalIncomeFrequency ?? "annual", tax_state: value.taxState,
        tax_filing_status: value.taxFilingStatus ?? "married_joint", include_payroll_taxes: value.includePayrollTaxes ?? false,
      },
      headers: forwardedSessionHeaders(request),
    });
    if (!response.ok || !data) return NextResponse.json({ message: apiErrorMessage(error, "We could not add that recurring item.") }, { status: response.status });
    return NextResponse.json({ templateId: data.id, name: data.name, monthlyAmount: data.monthly_amount ?? null }, { status: 201 });
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}
