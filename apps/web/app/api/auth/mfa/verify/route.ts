import { loginResultSchema, mfaVerifyRequestSchema } from "@clearpath/validation";
import { NextResponse } from "next/server";

import {
  apiErrorMessage,
  clearPathApiClient,
  forwardedSessionHeaders,
  jsonWithSessionCookie,
} from "@/lib/server-api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  let payload: unknown;
  try {
    payload = await request.json();
  } catch {
    return NextResponse.json({ message: "Enter your verification code." }, { status: 400 });
  }

  const parsed = mfaVerifyRequestSchema.safeParse(payload);
  if (!parsed.success) {
    return NextResponse.json(
      { message: parsed.error.issues[0]?.message ?? "Check your verification code." },
      { status: 422 },
    );
  }

  const client = clearPathApiClient();
  try {
    const { data, error, response } = await client.POST("/v1/auth/mfa/verify", {
      body: parsed.data,
      headers: forwardedSessionHeaders(request),
    });
    if (!response.ok || !data) {
      return NextResponse.json(
        { message: apiErrorMessage(error, "Your verification code was not accepted.") },
        { status: response.status },
      );
    }

    const result = loginResultSchema.safeParse({ nextStep: data.next_step });
    if (!result.success) {
      return NextResponse.json(
        { message: "ClearPath returned an invalid sign-in destination." },
        { status: 502 },
      );
    }
    return jsonWithSessionCookie(result.data, response);
  } catch {
    return NextResponse.json(
      { message: "ClearPath is temporarily unavailable. Please try again." },
      { status: 503 },
    );
  }
}
