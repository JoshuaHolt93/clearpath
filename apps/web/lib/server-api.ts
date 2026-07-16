import { createClearPathClient } from "@clearpath/api-client";
import { NextResponse } from "next/server";

export function clearPathApiClient() {
  const apiUrl = (process.env.CLEARPATH_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");
  return createClearPathClient(apiUrl);
}

export function forwardedSessionHeaders(request: Request): HeadersInit {
  const cookie = request.headers.get("cookie");
  return cookie ? { cookie } : {};
}

export function apiErrorMessage(error: unknown, fallback: string): string {
  if (!error || typeof error !== "object" || !("detail" in error)) {
    return fallback;
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
  return fallback;
}

export function jsonWithSessionCookie(
  payload: unknown,
  sourceResponse: Response,
  init?: { status?: number },
): NextResponse {
  const response = NextResponse.json(payload, init);
  const sessionCookie = sourceResponse.headers.get("set-cookie");
  if (sessionCookie) {
    response.headers.append("set-cookie", sessionCookie);
  }
  response.headers.set("cache-control", "no-store");
  return response;
}
