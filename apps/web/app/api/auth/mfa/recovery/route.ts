import { loginResultSchema, mfaRecoveryRequestSchema } from "@clearpath/validation";
import { NextResponse } from "next/server";

import {
  apiErrorMessage,
  clearPathApiClient,
  forwardedSessionHeaders,
  jsonWithSessionCookie,
} from "@/lib/server-api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const client = clearPathApiClient();
  try {
    const { data, error, response } = await client.GET("/v1/auth/mfa/recovery/challenge", {
      headers: forwardedSessionHeaders(request),
    });
    if (!response.ok || !data) {
      return NextResponse.json(
        { message: apiErrorMessage(error, "Your pending sign-in session is unavailable.") },
        { status: response.status },
      );
    }
    const webResponse = NextResponse.json({ available: data.available });
    webResponse.headers.set("cache-control", "no-store");
    return webResponse;
  } catch {
    return NextResponse.json(
      { message: "ClearPath is temporarily unavailable. Please try again." },
      { status: 503 },
    );
  }
}

export async function POST(request: Request) {
  let payload: unknown;
  try {
    payload = await request.json();
  } catch {
    return NextResponse.json({ message: "Enter a recovery code." }, { status: 400 });
  }

  const parsed = mfaRecoveryRequestSchema.safeParse(payload);
  if (!parsed.success) {
    return NextResponse.json(
      { message: parsed.error.issues[0]?.message ?? "Check your recovery code." },
      { status: 422 },
    );
  }

  const client = clearPathApiClient();
  try {
    const { data, error, response } = await client.POST("/v1/auth/mfa/recovery", {
      body: parsed.data,
      headers: forwardedSessionHeaders(request),
    });
    if (!response.ok || !data) {
      return NextResponse.json(
        { message: apiErrorMessage(error, "Your recovery code was not accepted.") },
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
