import { NextResponse } from "next/server";
import { plaidLinkEventSchema } from "@clearpath/validation";

import { clearPathApiClient, forwardedSessionHeaders } from "@/lib/server-api";

export async function POST(request: Request) {
  const parsed = plaidLinkEventSchema.safeParse(await request.json().catch(() => null));
  if (!parsed.success) {
    return NextResponse.json({ ok: false }, { status: 422 });
  }
  try {
    const { response } = await clearPathApiClient().POST("/v1/plaid/link-events", {
      body: parsed.data,
      headers: forwardedSessionHeaders(request),
    });
    return NextResponse.json({ ok: response.ok }, { status: response.status });
  } catch {
    return NextResponse.json({ ok: false }, { status: 503 });
  }
}
