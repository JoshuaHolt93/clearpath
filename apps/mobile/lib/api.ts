import { createClearPathClient } from "@clearpath/api-client";
import Constants from "expo-constants";

import { clearSessionToken, loadSessionToken } from "./session-store";

// Typed API client for the mobile app. It reuses the SAME generated openapi
// client the web BFF uses (@clearpath/api-client), so every request/response is
// typed against the FastAPI OpenAPI schema and stays in lockstep with the
// backend. Unlike web, mobile talks to the API DIRECTLY (no BFF): it attaches
// the stored JWT as an Authorization: Bearer header via openapi-fetch middleware.

export function apiBaseUrl(): string {
  const configured = (Constants.expoConfig?.extra as { clearpathApiUrl?: string } | undefined)?.clearpathApiUrl;
  // EXPO_PUBLIC_* env vars are inlined at build time and win over app config.
  return (process.env.EXPO_PUBLIC_API_URL ?? configured ?? "http://127.0.0.1:8000").replace(/\/$/, "");
}

// A 401 from the API means the stored token is invalid/expired; callers should
// treat this as "signed out". We surface it by clearing the token and letting
// the auth context redirect to the login screen on its next check.
export class UnauthorizedError extends Error {
  constructor() {
    super("Your session has expired. Please sign in again.");
    this.name = "UnauthorizedError";
  }
}

let client: ReturnType<typeof createClearPathClient> | null = null;

export function clearPathClient() {
  if (client) return client;
  client = createClearPathClient(apiBaseUrl());
  client.use({
    async onRequest({ request }) {
      const token = await loadSessionToken();
      if (token) {
        request.headers.set("Authorization", `Bearer ${token}`);
      }
      return request;
    },
    async onResponse({ response }) {
      if (response.status === 401) {
        await clearSessionToken();
      }
      return response;
    },
  });
  return client;
}

// Convenience: turn a FastAPI error `detail` (string | {message} | [{msg}]) into
// a user-facing sentence, mirroring the web BFF's apiErrorMessage helper.
export function apiErrorMessage(error: unknown, fallback: string): string {
  if (!error || typeof error !== "object" || !("detail" in error)) return fallback;
  const detail = (error as { detail?: unknown }).detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (detail && typeof detail === "object" && "message" in detail) {
    const message = String((detail as { message?: unknown }).message ?? "").trim();
    if (message) return message;
  }
  if (Array.isArray(detail)) {
    const messages = detail.map((item) => (item && typeof item === "object" && "msg" in item ? String(item.msg) : "")).filter(Boolean);
    if (messages.length) return messages.join(" ");
  }
  return fallback;
}
