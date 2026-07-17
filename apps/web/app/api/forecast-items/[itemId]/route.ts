import { forecastItemInputSchema, planningDeleteInputSchema } from "@clearpath/validation";
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
  if (!itemId) return NextResponse.json({ message: "One-time expense not found." }, { status: 404 });
  const parsed = forecastItemInputSchema.safeParse(await request.json().catch(() => null));
  if (!parsed.success) return NextResponse.json({ message: parsed.error.issues[0]?.message ?? "Check the one-time expense details." }, { status: 422 });
  const value = parsed.data;
  try {
    const { data, error, response } = await clearPathApiClient().PATCH("/v1/forecast-items/{item_id}", {
      params: { path: { item_id: itemId } },
      body: { item_date: value.itemDate, description: value.description, amount: value.amount, item_type: value.itemType, category_label: value.categoryLabel, notes: value.notes },
      headers: forwardedSessionHeaders(request),
    });
    if (!response.ok || !data) return NextResponse.json({ message: apiErrorMessage(error, "We could not update that one-time expense.") }, { status: response.status });
    return NextResponse.json({ itemId: data.id, description: data.description, amount: data.amount });
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}

export async function DELETE(request: Request, context: Context) {
  const itemId = positiveId((await context.params).itemId);
  if (!itemId) return NextResponse.json({ message: "One-time expense not found." }, { status: 404 });
  const parsed = planningDeleteInputSchema.safeParse(await request.json().catch(() => null));
  if (!parsed.success) return NextResponse.json({ message: "Confirm the one-time expense removal." }, { status: 422 });
  try {
    const { data, error, response } = await clearPathApiClient().DELETE("/v1/forecast-items/{item_id}", {
      params: { path: { item_id: itemId } }, body: { confirm: true }, headers: forwardedSessionHeaders(request),
    });
    if (!response.ok || !data) return NextResponse.json({ message: apiErrorMessage(error, "We could not remove that one-time expense.") }, { status: response.status });
    return NextResponse.json({ deletedItemId: data.deleted_item_id });
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}
