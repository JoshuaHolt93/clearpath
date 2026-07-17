import { cashProjectionRoleInputSchema } from "@clearpath/validation";
import { NextResponse } from "next/server";

import { apiErrorMessage, clearPathApiClient, forwardedSessionHeaders } from "@/lib/server-api";

export const runtime = "nodejs";
type Context = { params: Promise<{ accountId: string }> };

export async function PATCH(request: Request, context: Context) {
  const accountId = Number((await context.params).accountId);
  if (!Number.isInteger(accountId) || accountId <= 0) return NextResponse.json({ message: "Account not found." }, { status: 404 });
  const parsed = cashProjectionRoleInputSchema.safeParse(await request.json().catch(() => null));
  if (!parsed.success) return NextResponse.json({ message: parsed.error.issues[0]?.message ?? "Choose an operating-cash setting." }, { status: 422 });
  try {
    const { data, error, response } = await clearPathApiClient().PATCH("/v1/accounts/{account_id}/cash-projection-role", {
      params: { path: { account_id: accountId } },
      body: { cash_projection_role: parsed.data.cashProjectionRole },
      headers: forwardedSessionHeaders(request),
    });
    if (!response.ok || !data) return NextResponse.json({ message: apiErrorMessage(error, "We could not update that operating-cash setting.") }, { status: response.status });
    return NextResponse.json({ accountId: data.id, cashProjectionRole: data.cash_projection_role });
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}
