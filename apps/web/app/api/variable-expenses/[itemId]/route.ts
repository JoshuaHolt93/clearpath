import { planningAmountInputSchema, planningDeleteInputSchema, variableExpenseInputSchema } from "@clearpath/validation";
import { NextResponse } from "next/server";

import { apiErrorMessage, clearPathApiClient, forwardedSessionHeaders } from "@/lib/server-api";

export const runtime = "nodejs";
type Context = { params: Promise<{ itemId: string }> };

function positiveId(value: string): number | null {
  const id = Number(value);
  return Number.isInteger(id) && id > 0 ? id : null;
}

export async function PATCH(request: Request, context: Context) {
  const itemId = positiveId((await context.params).itemId);
  if (!itemId) return NextResponse.json({ message: "Flexible budget not found." }, { status: 404 });
  const raw = await request.json().catch(() => null);
  const amountOnly = Boolean(raw && typeof raw === "object" && "monthlyTarget" in raw);
  const parsed = amountOnly ? planningAmountInputSchema.safeParse(raw) : variableExpenseInputSchema.safeParse(raw);
  if (!parsed.success) return NextResponse.json({ message: parsed.error.issues[0]?.message ?? "Check the flexible budget details." }, { status: 422 });
  const body = amountOnly
    ? { monthly_target: (parsed.data as { monthlyTarget: number }).monthlyTarget, name: "", frequency: "monthly", use_specific_date: false }
    : (() => {
        const value = parsed.data as ReturnType<typeof variableExpenseInputSchema.parse>;
        return {
          name: value.name, amount: value.amount, frequency: value.frequency,
          use_specific_date: value.useSpecificDate, specific_date: value.specificDate,
          days_of_week: value.daysOfWeek, category_label: value.categoryLabel, notes: value.notes,
        };
      })();
  try {
    const { data, error, response } = await clearPathApiClient().PATCH("/v1/variable-expenses/{item_id}", {
      params: { path: { item_id: itemId } }, body, headers: forwardedSessionHeaders(request),
    });
    if (!response.ok || !data) return NextResponse.json({ message: apiErrorMessage(error, "We could not update that flexible budget.") }, { status: response.status });
    return NextResponse.json({ itemId: data.id, name: data.name, monthlyAmount: data.monthly_amount ?? null });
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}

export async function DELETE(request: Request, context: Context) {
  const itemId = positiveId((await context.params).itemId);
  if (!itemId) return NextResponse.json({ message: "Flexible budget not found." }, { status: 404 });
  const parsed = planningDeleteInputSchema.safeParse(await request.json().catch(() => null));
  if (!parsed.success) return NextResponse.json({ message: "Confirm the flexible budget removal." }, { status: 422 });
  try {
    const { data, error, response } = await clearPathApiClient().DELETE("/v1/variable-expenses/{item_id}", {
      params: { path: { item_id: itemId } }, body: { confirm: true }, headers: forwardedSessionHeaders(request),
    });
    if (!response.ok || !data) return NextResponse.json({ message: apiErrorMessage(error, "We could not remove that flexible budget.") }, { status: response.status });
    return NextResponse.json({ deletedItemId: data.deleted_item_id });
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}
