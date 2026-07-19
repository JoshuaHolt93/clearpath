import { loanPlanUpdateInputSchema } from "@clearpath/validation";
import { NextResponse } from "next/server";

import { mapLoanDetail, mapLoanResource } from "@/lib/loan-plans";
import { apiErrorMessage, clearPathApiClient, forwardedSessionHeaders } from "@/lib/server-api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type Context = { params: Promise<{ itemId: string }> };

export async function GET(request: Request, context: Context) {
  const { itemId } = await context.params;
  const headers = forwardedSessionHeaders(request);
  try {
    const [loan, me] = await Promise.all([
      clearPathApiClient().GET("/v1/loan-plans/{fixed_expense_item_id}", { params: { path: { fixed_expense_item_id: Number(itemId) } }, headers }),
      clearPathApiClient().GET("/v1/me", { headers }),
    ]);
    if (!loan.response.ok || !loan.data) return NextResponse.json({ message: apiErrorMessage(loan.error, "We could not load that loan plan.") }, { status: loan.response.status });
    if (!me.response.ok || !me.data) return NextResponse.json({ message: apiErrorMessage(me.error, "We could not load your session.") }, { status: me.response.status });
    const mapped = mapLoanDetail(loan.data, me.data);
    if (!mapped.success) return NextResponse.json({ message: "Loan plan data did not match the expected contract." }, { status: 502 });
    return NextResponse.json(mapped.data, { headers: { "cache-control": "no-store" } });
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}

export async function PATCH(request: Request, context: Context) {
  const { itemId } = await context.params;
  const parsed = loanPlanUpdateInputSchema.safeParse(await request.json().catch(() => null));
  if (!parsed.success) return NextResponse.json({ message: parsed.error.issues[0]?.message ?? "Check the loan details." }, { status: 422 });
  const value = parsed.data;
  try {
    const { data, error, response } = await clearPathApiClient().PATCH("/v1/loan-plans/{fixed_expense_item_id}", {
      params: { path: { fixed_expense_item_id: Number(itemId) } },
      body: { principal_balance: value.principalBalance, collateral_value: value.collateralValue, annual_interest_rate: value.annualInterestRate, term_value: value.termValue, term_unit: value.termUnit, regular_payment: value.regularPayment, extra_payment_one: value.extraPaymentOne, extra_payment_two: value.extraPaymentTwo, selected_scenario: value.selectedScenario, notes: value.notes },
      headers: forwardedSessionHeaders(request),
    });
    if (!response.ok || !data) return NextResponse.json({ message: apiErrorMessage(error, "We could not save that loan plan.") }, { status: response.status });
    const mapped = mapLoanResource(data);
    if (!mapped.success) return NextResponse.json({ message: "Loan plan data did not match the expected contract." }, { status: 502 });
    return NextResponse.json(mapped.data);
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}
