import { monthlyPlanBaselineInputSchema } from "@clearpath/validation";
import { NextResponse } from "next/server";

import { apiErrorMessage, clearPathApiClient, forwardedSessionHeaders } from "@/lib/server-api";

export const runtime = "nodejs";

export async function PATCH(request: Request) {
  const parsed = monthlyPlanBaselineInputSchema.safeParse(await request.json().catch(() => null));
  if (!parsed.success) return NextResponse.json({ message: parsed.error.issues[0]?.message ?? "Check the planning baseline." }, { status: 422 });
  const value = parsed.data;
  try {
    const { data, error, response } = await clearPathApiClient().PATCH("/v1/monthly-plan/baseline", {
      body: {
        baseline_scope: value.baselineScope, household_name: value.householdName,
        income_amount: value.incomeAmount, income_basis: value.incomeBasis, income_type: value.incomeType,
        paycheck_cadence: value.paycheckCadence, next_pay_date: value.nextPayDate,
        second_date: value.secondDate, recurring_days_of_week: value.recurringDaysOfWeek,
        recurring_monthly_week_numbers: value.recurringMonthlyWeekNumbers,
        recurring_monthly_weekday: value.recurringMonthlyWeekday,
        hourly_hours_per_week: value.hourlyHoursPerWeek,
        additional_income_amount: value.additionalIncomeAmount,
        additional_income_frequency: value.additionalIncomeFrequency,
        tax_state: value.taxState, tax_filing_status: value.taxFilingStatus,
        tax_additional_label: value.taxAdditionalLabel,
        tax_additional_type: value.taxAdditionalType,
        tax_additional_rate: value.taxAdditionalRate,
        tax_additional_monthly_amount: value.taxAdditionalMonthlyAmount,
        include_payroll_taxes: value.includePayrollTaxes, notes: value.notes,
        view: value.view, section: value.section,
      },
      headers: forwardedSessionHeaders(request),
    });
    if (!response.ok || !data) return NextResponse.json({ message: apiErrorMessage(error, "We could not save the planning baseline.") }, { status: response.status });
    return NextResponse.json({ saved: true, householdName: data.profile.household_name ?? null, monthlyIncome: data.plan.income });
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}
