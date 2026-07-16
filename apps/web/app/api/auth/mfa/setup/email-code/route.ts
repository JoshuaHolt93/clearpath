import { mfaEmailCodeResultSchema } from "@clearpath/validation";
import { NextResponse } from "next/server";

import {
  apiErrorMessage,
  clearPathApiClient,
  forwardedSessionHeaders,
  setMfaEmailChallengeCookie,
} from "@/lib/server-api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const client = clearPathApiClient();
  try {
    const { data, error, response } = await client.POST("/v1/auth/mfa/setup/email-code", {
      body: { purpose: "setup" },
      headers: forwardedSessionHeaders(request),
    });
    if (!response.ok || !data) {
      return NextResponse.json(
        { message: apiErrorMessage(error, "An email verification code could not be sent.") },
        { status: response.status },
      );
    }
    const result = mfaEmailCodeResultSchema.safeParse({
      sent: data.sent,
      reason: data.reason,
    });
    if (!result.success) {
      return NextResponse.json({ message: "ClearPath returned an invalid email-code result." }, { status: 502 });
    }
    const webResponse = NextResponse.json(result.data);
    webResponse.headers.set("cache-control", "no-store");
    setMfaEmailChallengeCookie(webResponse, data.challenge_token);
    return webResponse;
  } catch {
    return NextResponse.json(
      { message: "ClearPath is temporarily unavailable. Please try again." },
      { status: 503 },
    );
  }
}
