import { plaidLinkTokenResultSchema } from "@clearpath/validation";
import { NextResponse } from "next/server";

import { apiErrorMessage, clearPathApiClient, forwardedSessionHeaders } from "@/lib/server-api";

export async function POST(request: Request) {
  try {
    const { data, error, response } = await clearPathApiClient().POST("/v1/plaid/link-token", {
      headers: forwardedSessionHeaders(request),
    });
    if (!response.ok || !data) {
      return NextResponse.json(
        { message: apiErrorMessage(error, "Plaid could not start a secure bank connection.") },
        { status: response.status },
      );
    }
    const parsed = plaidLinkTokenResultSchema.safeParse({
      linkToken: data.link_token,
      consentToken: data.consent_token,
    });
    if (!parsed.success) {
      return NextResponse.json({ message: "ClearPath returned invalid Plaid setup details." }, { status: 502 });
    }
    return NextResponse.json(parsed.data, { headers: { "cache-control": "no-store" } });
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}
