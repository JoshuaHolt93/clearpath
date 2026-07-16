import {
  passwordResetConfirmRequestSchema,
  passwordResetConfirmResultSchema,
  passwordResetTokenResultSchema,
} from "@clearpath/validation";
import { NextResponse } from "next/server";

import { apiErrorMessage, clearPathApiClient, jsonWithSessionCookie } from "@/lib/server-api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type RouteContext = { params: Promise<{ token: string }> };

export async function GET(_request: Request, context: RouteContext) {
  const { token } = await context.params;
  try {
    const { data, error, response } = await clearPathApiClient().GET("/v1/auth/password-reset/{token}", {
      params: { path: { token } },
    });
    if (!response.ok || !data) {
      return NextResponse.json(
        { message: apiErrorMessage(error, "That password reset link is invalid or expired.") },
        { status: response.status },
      );
    }
    const result = passwordResetTokenResultSchema.safeParse(data);
    if (!result.success) {
      return NextResponse.json({ message: "ClearPath returned invalid reset information." }, { status: 502 });
    }
    const webResponse = NextResponse.json(result.data);
    webResponse.headers.set("cache-control", "no-store");
    return webResponse;
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}

export async function POST(request: Request, context: RouteContext) {
  const { token } = await context.params;
  let payload: unknown;
  try {
    payload = await request.json();
  } catch {
    return NextResponse.json({ message: "Enter and confirm your new password." }, { status: 400 });
  }
  const parsed = passwordResetConfirmRequestSchema.safeParse(payload);
  if (!parsed.success) {
    return NextResponse.json(
      { message: parsed.error.issues[0]?.message ?? "Check your new password." },
      { status: 422 },
    );
  }
  try {
    const { data, error, response } = await clearPathApiClient().POST("/v1/auth/password-reset/{token}", {
      params: { path: { token } },
      body: parsed.data,
    });
    if (!response.ok || !data) {
      return NextResponse.json(
        { message: apiErrorMessage(error, "We could not reset your password. Please request a new link.") },
        { status: response.status },
      );
    }
    const result = passwordResetConfirmResultSchema.safeParse(data);
    if (!result.success) {
      return NextResponse.json({ message: "ClearPath returned an invalid reset result." }, { status: 502 });
    }
    return jsonWithSessionCookie(result.data, response);
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}
