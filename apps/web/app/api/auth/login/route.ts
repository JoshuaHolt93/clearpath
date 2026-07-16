import { createClearPathClient } from "@clearpath/api-client";
import { loginRequestSchema, loginResultSchema } from "@clearpath/validation";
import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function apiErrorMessage(error: unknown): string {
  if (!error || typeof error !== "object" || !("detail" in error)) {
    return "We could not sign you in. Please check your details and try again.";
  }
  const detail = (error as { detail?: unknown }).detail;
  if (typeof detail === "string" && detail.trim()) {
    return detail;
  }
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => (item && typeof item === "object" && "msg" in item ? String(item.msg) : ""))
      .filter(Boolean);
    if (messages.length) {
      return messages.join(" ");
    }
  }
  return "We could not sign you in. Please check your details and try again.";
}

export async function POST(request: Request) {
  let payload: unknown;
  try {
    payload = await request.json();
  } catch {
    return NextResponse.json({ message: "Enter your email and password." }, { status: 400 });
  }

  const parsed = loginRequestSchema.safeParse(payload);
  if (!parsed.success) {
    return NextResponse.json(
      { message: parsed.error.issues[0]?.message ?? "Check your sign-in details." },
      { status: 422 },
    );
  }

  const apiUrl = (process.env.CLEARPATH_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");
  const client = createClearPathClient(apiUrl);

  try {
    const { data, error, response } = await client.POST("/v1/auth/login", { body: parsed.data });
    if (!response.ok || !data) {
      return NextResponse.json({ message: apiErrorMessage(error) }, { status: response.status });
    }

    const loginResult = loginResultSchema.safeParse({ nextStep: data.next_step });
    if (!loginResult.success) {
      return NextResponse.json({ message: "ClearPath returned an invalid sign-in destination." }, { status: 502 });
    }

    const webResponse = NextResponse.json(loginResult.data);
    const sessionCookie = response.headers.get("set-cookie");
    if (sessionCookie) {
      webResponse.headers.append("set-cookie", sessionCookie);
    }
    webResponse.headers.set("cache-control", "no-store");
    return webResponse;
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}
