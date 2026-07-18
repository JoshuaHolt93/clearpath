import { duplicateMergeInputSchema } from "@clearpath/validation";
import { NextResponse } from "next/server";

import { apiErrorMessage, clearPathApiClient, forwardedSessionHeaders } from "@/lib/server-api";

export async function POST(request: Request) {
  const parsed = duplicateMergeInputSchema.safeParse(await request.json().catch(() => null));
  if (!parsed.success) return NextResponse.json({ message: "Choose the two transactions to merge." }, { status: 422 });
  try {
    const { data, error, response } = await clearPathApiClient().POST("/v1/transactions/duplicates/merge", { body: { first_transaction_id: parsed.data.firstTransactionId, second_transaction_id: parsed.data.secondTransactionId }, headers: forwardedSessionHeaders(request) });
    if (!response.ok || !data) return NextResponse.json({ message: apiErrorMessage(error, "We could not merge those transactions.") }, { status: response.status });
    return NextResponse.json({ merged: data.merged, deletedTransactionId: data.deleted_transaction_id });
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}
