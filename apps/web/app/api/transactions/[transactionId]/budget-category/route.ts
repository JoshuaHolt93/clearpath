import { NextResponse } from "next/server";

import { apiErrorMessage, clearPathApiClient, forwardedSessionHeaders } from "@/lib/server-api";

type Context = { params: Promise<{ transactionId: string }> };

export async function POST(request: Request, context: Context) {
  const transactionId = Number((await context.params).transactionId);
  if (!Number.isInteger(transactionId) || transactionId < 1) return NextResponse.json({ message: "Transaction not found." }, { status: 404 });
  try {
    const { data, error, response } = await clearPathApiClient().POST("/v1/transactions/{transaction_id}/budget-category", { params: { path: { transaction_id: transactionId } }, headers: forwardedSessionHeaders(request) });
    if (!response.ok || !data) return NextResponse.json({ message: apiErrorMessage(error, "We could not create that budget.") }, { status: response.status });
    return NextResponse.json({ categoryId: data.category.id, target: data.target });
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}
