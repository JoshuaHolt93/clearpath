import { passwordResetRequestResultSchema, passwordResetRequestSchema } from "@clearpath/validation";
import { NextResponse } from "next/server";

import { apiErrorMessage, clearPathApiClient } from "@/lib/server-api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  let payload: unknown;
  try {
    payload = await request.json();
  } catch {
    return NextResponse.json({ message: "Enter your email address." }, { status: 400 });
  }
  const parsed = passwordResetRequestSchema.safeParse(payload);
  if (!parsed.success) {
    return NextResponse.json(
      { message: parsed.error.issues[0]?.message ?? "Enter a valid email address." },
      { status: 422 },
    );
  }
  try {
    const { data, error, response } = await clearPathApiClient().POST("/v1/auth/password-reset/request", {
      body: parsed.data,
    });
    if (!response.ok || !data) {
      return NextResponse.json(
        { message: apiErrorMessage(error, "We could not request a reset link. Please try again.") },
        { status: response.status },
      );
    }
    const result = passwordResetRequestResultSchema.safeParse({
      message: data.message,
      resetUrl: data.reset_token ? `/reset-password/${encodeURIComponent(data.reset_token)}` : null,
    });
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
