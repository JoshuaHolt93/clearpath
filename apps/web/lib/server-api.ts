import { createClearPathClient } from "@clearpath/api-client";
import { NextResponse } from "next/server";

export const MFA_EMAIL_CHALLENGE_COOKIE = "clearpath_mfa_email_challenge";
const MFA_EMAIL_CHALLENGE_MAX_AGE_SECONDS = 10 * 60;

export function clearPathApiClient() {
  const apiUrl = (process.env.CLEARPATH_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");
  return createClearPathClient(apiUrl);
}

export function forwardedSessionHeaders(request: Request): HeadersInit {
  const cookie = request.headers.get("cookie");
  return cookie ? { cookie } : {};
}

export function requestCookieValue(request: Request, name: string): string | null {
  const cookies = request.headers.get("cookie") ?? "";
  for (const pair of cookies.split(";")) {
    const separator = pair.indexOf("=");
    if (separator < 0) {
      continue;
    }
    const cookieName = pair.slice(0, separator).trim();
    if (cookieName === name) {
      return decodeURIComponent(pair.slice(separator + 1).trim());
    }
  }
  return null;
}

export function setMfaEmailChallengeCookie(response: NextResponse, token: string | null | undefined) {
  if (!token) {
    response.headers.append(
      "set-cookie",
      `${MFA_EMAIL_CHALLENGE_COOKIE}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0; Expires=Thu, 01 Jan 1970 00:00:00 GMT`,
    );
    return;
  }
  const secure = process.env.NODE_ENV === "production" ? "; Secure" : "";
  response.headers.append(
    "set-cookie",
    `${MFA_EMAIL_CHALLENGE_COOKIE}=${encodeURIComponent(token)}; Path=/; HttpOnly; SameSite=Lax; Max-Age=${MFA_EMAIL_CHALLENGE_MAX_AGE_SECONDS}${secure}`,
  );
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
