import { NextResponse } from "next/server";

import { mapLoanDirectory } from "@/lib/loan-plans";
import { apiErrorMessage, clearPathApiClient, forwardedSessionHeaders } from "@/lib/server-api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const headers = forwardedSessionHeaders(request);
  try {
    const [loans, me] = await Promise.all([clearPathApiClient().GET("/v1/loan-plans", { headers }), clearPathApiClient().GET("/v1/me", { headers })]);
    if (!loans.response.ok || !loans.data) return NextResponse.json({ message: apiErrorMessage(loans.error, "We could not load mortgage and loan planning.") }, { status: loans.response.status });
    if (!me.response.ok || !me.data) return NextResponse.json({ message: apiErrorMessage(me.error, "We could not load your session.") }, { status: me.response.status });
    const mapped = mapLoanDirectory(loans.data, me.data);
    if (!mapped.success) return NextResponse.json({ message: "Loan planning data did not match the expected contract." }, { status: 502 });
    return NextResponse.json(mapped.data, { headers: { "cache-control": "no-store" } });
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}
