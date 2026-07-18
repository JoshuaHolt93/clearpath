import { transactionSplitsInputSchema } from "@clearpath/validation";
import { NextResponse } from "next/server";

import { apiErrorMessage, clearPathApiClient, forwardedSessionHeaders } from "@/lib/server-api";

type Context = { params: Promise<{ transactionId: string }> };

export async function PATCH(request: Request, context: Context) {
  const transactionId = Number((await context.params).transactionId);
  if (!Number.isInteger(transactionId) || transactionId < 1) return NextResponse.json({ message: "Transaction not found." }, { status: 404 });
  const parsed = transactionSplitsInputSchema.safeParse(await request.json().catch(() => null));
  if (!parsed.success) return NextResponse.json({ message: parsed.error.issues[0]?.message ?? "Check the split details." }, { status: 422 });
  try {
    const { data, error, response } = await clearPathApiClient().PATCH("/v1/transactions/{transaction_id}/splits", {
      params: { path: { transaction_id: transactionId } },
      body: { clear_splits: parsed.data.clearSplits, splits: parsed.data.splits.map((row) => ({ category_id: row.categoryId, amount: row.amount, notes: row.notes })) },
      headers: forwardedSessionHeaders(request),
    });
    if (!response.ok || !data) return NextResponse.json({ message: apiErrorMessage(error, "We could not save that split.") }, { status: response.status });
    return NextResponse.json({ transactionId: data.id, splitCount: data.splits?.length ?? 0 });
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}
