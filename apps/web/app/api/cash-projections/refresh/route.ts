import { cashProjectionQueryInputSchema } from "@clearpath/validation";
import { NextResponse } from "next/server";

import { mapCashProjection } from "@/lib/cash-projection";
import { apiErrorMessage, clearPathApiClient, forwardedSessionHeaders } from "@/lib/server-api";

export const runtime = "nodejs";

export async function POST(request: Request) {
  const parsed = cashProjectionQueryInputSchema.safeParse(await request.json().catch(() => ({})));
  if (!parsed.success) return NextResponse.json({ message: parsed.error.issues[0]?.message ?? "Choose a valid projection range." }, { status: 422 });
  try {
    const { data, error, response } = await clearPathApiClient().POST("/v1/cash-projections/refresh", {
      body: {
        month: parsed.data.month ?? null,
        horizon: parsed.data.horizon ?? null,
        view: parsed.data.view,
        start_date: parsed.data.startDate ?? null,
        end_date: parsed.data.endDate ?? null,
      },
      headers: forwardedSessionHeaders(request),
    });
    if (!response.ok || !data) return NextResponse.json({ message: apiErrorMessage(error, "We could not refresh connected balances.") }, { status: response.status });
    const mapped = mapCashProjection(data);
    if (!mapped.success) return NextResponse.json({ message: "Refreshed cash projection data did not match the expected contract." }, { status: 502 });
    return NextResponse.json(mapped.data);
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}
