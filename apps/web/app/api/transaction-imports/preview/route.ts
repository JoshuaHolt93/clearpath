import { transactionImportPreviewInputSchema } from "@clearpath/validation";
import { NextResponse } from "next/server";

import { apiErrorMessage, clearPathApiClient, forwardedSessionHeaders } from "@/lib/server-api";
import { mapTransactionImportPreview } from "@/lib/transactions";

export async function POST(request: Request) {
  const parsed = transactionImportPreviewInputSchema.safeParse(await request.json().catch(() => null));
  if (!parsed.success) return NextResponse.json({ message: parsed.error.issues[0]?.message ?? "Check the CSV mapping." }, { status: 422 });
  const value = parsed.data;
  try {
    const { data, error, response } = await clearPathApiClient().POST("/v1/transaction-imports/preview", { body: {
      csv_text: value.csvText, fallback_account: value.fallbackAccount,
      mapping: value.mapping ? { date: value.mapping.date, description: value.mapping.description, amount: value.mapping.amount, debit: value.mapping.debit, credit: value.mapping.credit, account: value.mapping.account } : null,
    }, headers: forwardedSessionHeaders(request) });
    if (!response.ok || !data) return NextResponse.json({ message: apiErrorMessage(error, "We could not preview that CSV.") }, { status: response.status });
    const mapped = mapTransactionImportPreview(data);
    if (!mapped.success) return NextResponse.json({ message: "Import preview did not match the expected contract." }, { status: 502 });
    return NextResponse.json(mapped.data);
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}
