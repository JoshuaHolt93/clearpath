import { beforeEach, describe, expect, it, vi } from "vitest";

import { GET, POST } from "./[token]/route";

const apiGet = vi.hoisted(() => vi.fn());
const apiPost = vi.hoisted(() => vi.fn());

vi.mock("@clearpath/api-client", () => ({
  createClearPathClient: () => ({ GET: apiGet, POST: apiPost }),
}));

describe("household invitation BFF routes", () => {
  beforeEach(() => {
    apiGet.mockReset();
    apiPost.mockReset();
  });

  it("maps invitation details and forwards the current-session deletion cookie", async () => {
    apiGet.mockResolvedValue({
      data: {
        valid: true,
        email: "shared@example.com",
        household_name: "Parker Household",
        role: "viewer",
      },
      error: undefined,
      response: new Response(null, {
        status: 200,
        headers: { "set-cookie": "clearpath_session=; HttpOnly; Max-Age=0" },
      }),
    });
    const response = await GET(new Request("http://localhost"), {
      params: Promise.resolve({ token: "invite-token" }),
    });
    expect(await response.json()).toEqual({
      valid: true,
      email: "shared@example.com",
      householdName: "Parker Household",
      role: "viewer",
    });
    expect(response.headers.get("set-cookie")).toContain("Max-Age=0");
    expect(apiGet).toHaveBeenCalledWith("/v1/household-invites/{token}", {
      params: { path: { token: "invite-token" } },
    });
  });

  it("accepts the invite, forwards the pending-member cookie, and hides the token", async () => {
    apiPost.mockResolvedValue({
      data: { access_token: "server-only", next_step: "mfa_setup" },
      error: undefined,
      response: new Response(null, {
        status: 200,
        headers: { "set-cookie": "clearpath_session=server-only; HttpOnly; Max-Age=900" },
      }),
    });
    const response = await POST(new Request("http://localhost", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        display_name: "  Taylor Parker ",
        password: "SharedVault123!",
        confirm_password: "SharedVault123!",
        policy_acknowledgement: true,
      }),
    }), { params: Promise.resolve({ token: "invite-token" }) });
    expect(await response.json()).toEqual({ nextStep: "mfa_setup" });
    expect(response.headers.get("set-cookie")).toContain("HttpOnly");
    expect(apiPost).toHaveBeenCalledWith("/v1/household-invites/{token}/accept", {
      params: { path: { token: "invite-token" } },
      body: {
        display_name: "Taylor Parker",
        password: "SharedVault123!",
        confirm_password: "SharedVault123!",
        policy_acknowledgement: true,
      },
    });
  });

  it("rejects mismatched passwords before contacting FastAPI", async () => {
    const response = await POST(new Request("http://localhost", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        display_name: "Taylor",
        password: "SharedVault123!",
        confirm_password: "DifferentVault123!",
        policy_acknowledgement: true,
      }),
    }), { params: Promise.resolve({ token: "invite-token" }) });
    expect(response.status).toBe(422);
    expect(apiPost).not.toHaveBeenCalled();
  });
});
