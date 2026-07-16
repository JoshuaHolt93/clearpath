import { beforeEach, describe, expect, it, vi } from "vitest";

import { POST as requestReset } from "./password-reset/request/route";
import { GET as validateReset, POST as confirmReset } from "./password-reset/[token]/route";
import { POST as register } from "./register/route";

const apiGet = vi.hoisted(() => vi.fn());
const apiPost = vi.hoisted(() => vi.fn());

vi.mock("@clearpath/api-client", () => ({
  createClearPathClient: () => ({ GET: apiGet, POST: apiPost }),
}));

describe("registration and password-reset BFF routes", () => {
  beforeEach(() => {
    apiGet.mockReset();
    apiPost.mockReset();
  });

  it("registers through FastAPI and forwards only the httpOnly session cookie", async () => {
    apiPost.mockResolvedValue({
      data: { access_token: "server-only", next_step: "mfa_setup" },
      error: undefined,
      response: new Response(null, {
        status: 201,
        headers: { "set-cookie": "clearpath_session=server-only; HttpOnly; SameSite=Lax" },
      }),
    });
    const response = await register(new Request("http://localhost/api/auth/register", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        display_name: "  Jordan Parker ",
        household_name: "",
        email: "  JORDAN@example.com ",
        password: "CorrectHorse1!",
        policy_acknowledgement: true,
      }),
    }));

    expect(response.status).toBe(201);
    expect(await response.json()).toEqual({ nextStep: "mfa_setup" });
    expect(response.headers.get("set-cookie")).toContain("HttpOnly");
    expect(apiPost).toHaveBeenCalledWith("/v1/auth/register", {
      body: {
        display_name: "Jordan Parker",
        household_name: null,
        email: "jordan@example.com",
        password: "CorrectHorse1!",
        policy_acknowledgement: true,
        ethics_acknowledgement: false,
        legal_acknowledgement: false,
      },
    });
  });

  it("maps a development reset token to a web link without changing the generic message", async () => {
    apiPost.mockResolvedValue({
      data: { message: "If an account exists for that email, a password reset link has been sent.", reset_token: "signed-token" },
      error: undefined,
      response: new Response(null, { status: 200 }),
    });
    const response = await requestReset(new Request("http://localhost/api/auth/password-reset/request", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ email: "PERSON@example.com" }),
    }));

    expect(await response.json()).toEqual({
      message: "If an account exists for that email, a password reset link has been sent.",
      resetUrl: "/reset-password/signed-token",
    });
    expect(apiPost).toHaveBeenCalledWith("/v1/auth/password-reset/request", {
      body: { email: "person@example.com" },
    });
  });

  it("validates and confirms a reset token through the typed API paths", async () => {
    apiGet.mockResolvedValue({
      data: { valid: true, email: "person@example.com" },
      error: undefined,
      response: new Response(null, { status: 200 }),
    });
    const context = { params: Promise.resolve({ token: "signed-token" }) };
    const validated = await validateReset(new Request("http://localhost"), context);
    expect(await validated.json()).toEqual({ valid: true, email: "person@example.com" });
    expect(apiGet).toHaveBeenCalledWith("/v1/auth/password-reset/{token}", {
      params: { path: { token: "signed-token" } },
    });

    apiPost.mockResolvedValue({
      data: { ok: true },
      error: undefined,
      response: new Response(null, {
        status: 200,
        headers: { "set-cookie": "clearpath_session=; HttpOnly; Max-Age=0" },
      }),
    });
    const confirmed = await confirmReset(new Request("http://localhost", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ password: "NewCorrectHorse2!", confirm_password: "NewCorrectHorse2!" }),
    }), context);
    expect(await confirmed.json()).toEqual({ ok: true });
    expect(confirmed.headers.get("set-cookie")).toContain("Max-Age=0");
    expect(apiPost).toHaveBeenCalledWith("/v1/auth/password-reset/{token}", {
      params: { path: { token: "signed-token" } },
      body: { password: "NewCorrectHorse2!", confirm_password: "NewCorrectHorse2!" },
    });
  });

  it("rejects mismatched passwords before contacting FastAPI", async () => {
    const response = await confirmReset(new Request("http://localhost", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ password: "NewCorrectHorse2!", confirm_password: "DifferentHorse3!" }),
    }), { params: Promise.resolve({ token: "signed-token" }) });
    expect(response.status).toBe(422);
    expect(apiPost).not.toHaveBeenCalled();
  });
});
