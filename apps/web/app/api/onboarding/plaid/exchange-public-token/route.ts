import { plaidExchangeRequestSchema } from "@clearpath/validation";
import { NextResponse } from "next/server";

import { apiErrorMessage, clearPathApiClient, forwardedSessionHeaders } from "@/lib/server-api";

export async function POST(request: Request) {
  const parsed = plaidExchangeRequestSchema.safeParse(await request.json().catch(() => null));
  if (!parsed.success) {
    return NextResponse.json({ message: parsed.error.issues[0]?.message }, { status: 422 });
  }
  try {
    const { data, error, response } = await clearPathApiClient().POST("/v1/plaid/exchange-public-token", {
      body: parsed.data,
      headers: forwardedSessionHeaders(request),
    });
    if (!response.ok || !data) {
      return NextResponse.json(
        { message: apiErrorMessage(error, "Plaid connected, but ClearPath could not save it.") },
        { status: response.status },
      );
    }
    return NextResponse.json({ connected: true, plaidItemId: data.id });
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}
