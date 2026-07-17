import { planningAmountInputSchema, planningDeleteInputSchema, recurringTemplateInputSchema } from "@clearpath/validation";
import { NextResponse } from "next/server";

import { apiErrorMessage, clearPathApiClient, forwardedSessionHeaders } from "@/lib/server-api";

export const runtime = "nodejs";
type Context = { params: Promise<{ templateId: string }> };

function positiveId(value: string): number | null {
  const id = Number(value);
  return Number.isInteger(id) && id > 0 ? id : null;
}

export async function PATCH(request: Request, context: Context) {
  const templateId = positiveId((await context.params).templateId);
  if (!templateId) return NextResponse.json({ message: "Recurring item not found." }, { status: 404 });
  const raw = await request.json().catch(() => null);
  const amountOnly = Boolean(raw && typeof raw === "object" && "monthlyTarget" in raw);
  const parsed = amountOnly ? planningAmountInputSchema.safeParse(raw) : recurringTemplateInputSchema.safeParse(raw);
  if (!parsed.success) return NextResponse.json({ message: parsed.error.issues[0]?.message ?? "Check the recurring item details." }, { status: 422 });
  const body = amountOnly
    ? {
        monthly_target: (parsed.data as { monthlyTarget: number }).monthlyTarget,
        name: "", item_type: "expense", frequency: "monthly", income_adjustment: false,
        income_basis: "take_home", income_type: "salary", paycheck_cadence: "monthly",
        additional_income_frequency: "annual", tax_filing_status: "married_joint", include_payroll_taxes: false,
      }
    : (() => {
        const value = parsed.data as ReturnType<typeof recurringTemplateInputSchema.parse>;
        return {
          name: value.name, amount: value.amount, item_type: value.itemType, frequency: value.frequency,
          start_date: value.startDate, second_date: value.secondDate, recurring_days_of_week: value.recurringDaysOfWeek,
          recurring_monthly_week_numbers: value.recurringMonthlyWeekNumbers,
          recurring_monthly_weekday: value.recurringMonthlyWeekday, category_label: value.categoryLabel,
          notes: value.notes, income_adjustment: value.incomeAdjustment,
          income_basis: "take_home", income_type: "salary", paycheck_cadence: "monthly",
          additional_income_frequency: "annual", tax_filing_status: "married_joint", include_payroll_taxes: false,
        };
      })();
  try {
    const { data, error, response } = await clearPathApiClient().PATCH("/v1/recurring-templates/{template_id}", {
      params: { path: { template_id: templateId } }, body, headers: forwardedSessionHeaders(request),
    });
    if (!response.ok || !data) return NextResponse.json({ message: apiErrorMessage(error, "We could not update that recurring item.") }, { status: response.status });
    return NextResponse.json({ templateId: data.id, name: data.name, monthlyAmount: data.monthly_amount ?? null });
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}

export async function DELETE(request: Request, context: Context) {
  const templateId = positiveId((await context.params).templateId);
  if (!templateId) return NextResponse.json({ message: "Recurring item not found." }, { status: 404 });
  const parsed = planningDeleteInputSchema.safeParse(await request.json().catch(() => null));
  if (!parsed.success) return NextResponse.json({ message: "Confirm the recurring item removal." }, { status: 422 });
  try {
    const { data, error, response } = await clearPathApiClient().DELETE("/v1/recurring-templates/{template_id}", {
      params: { path: { template_id: templateId } }, body: { confirm: true }, headers: forwardedSessionHeaders(request),
    });
    if (!response.ok || !data) return NextResponse.json({ message: apiErrorMessage(error, "We could not remove that recurring item.") }, { status: response.status });
    return NextResponse.json({ deletedTemplateId: data.deleted_template_id });
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}
