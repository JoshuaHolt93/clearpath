import { NextResponse } from "next/server";

import { apiErrorMessage, clearPathApiClient, forwardedSessionHeaders } from "@/lib/server-api";
import { mapTransactionReview } from "@/lib/transactions";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function positiveInt(value: string | null, fallback: number) {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : fallback;
}

function intList(values: string[]) {
  return values.map(Number).filter((value) => Number.isInteger(value) && value > 0);
}

export async function GET(request: Request) {
  const url = new URL(request.url);
  const headers = forwardedSessionHeaders(request);
  try {
    const [transactions, me, plaid] = await Promise.all([
      clearPathApiClient().GET("/v1/transactions", {
        params: { query: {
          q: url.searchParams.get("q") ?? "", category_ids: intList(url.searchParams.getAll("category_id")),
          category_names: url.searchParams.get("category_names") ?? "", account_ids: intList(url.searchParams.getAll("account_id")),
          min_amount: url.searchParams.get("min_amount") ?? "", max_amount: url.searchParams.get("max_amount") ?? "",
          month: url.searchParams.get("month") ?? "", ids: url.searchParams.get("ids") ?? "",
          sort: url.searchParams.get("sort") ?? "date_desc", page: positiveInt(url.searchParams.get("page"), 1), per_page: 20,
        } }, headers,
      }),
      clearPathApiClient().GET("/v1/me", { headers }),
      clearPathApiClient().GET("/v1/plaid-items", { headers }),
    ]);
    if (!transactions.response.ok || !transactions.data) return NextResponse.json({ message: apiErrorMessage(transactions.error, "We could not load transactions.") }, { status: transactions.response.status });
    if (!me.response.ok || !me.data) return NextResponse.json({ message: apiErrorMessage(me.error, "We could not load your session.") }, { status: me.response.status });
    if (!plaid.response.ok || !plaid.data) return NextResponse.json({ message: apiErrorMessage(plaid.error, "We could not load connected accounts.") }, { status: plaid.response.status });
    const mapped = mapTransactionReview(transactions.data, me.data, plaid.data);
    if (!mapped.success) return NextResponse.json({ message: "Transaction data did not match the expected contract." }, { status: 502 });
    return NextResponse.json(mapped.data, { headers: { "cache-control": "no-store" } });
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}
