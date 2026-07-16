import { beforeEach, describe, expect, it, vi } from "vitest";

import { POST } from "./route";

const apiPost = vi.hoisted(() => vi.fn());

vi.mock("@clearpath/api-client", () => ({
  createClearPathClient: () => ({ POST: apiPost }),
}));

describe("POST /api/auth/login", () => {
  beforeEach(() => {
    apiPost.mockReset();
  });

  it("forwards the httpOnly session cookie but never exposes the token in JSON", async () => {
    apiPost.mockResolvedValue({
      data: {
        access_token: "server-only-token",
        token_type: "bearer",
        next_step: "dashboard",
      },
      error: undefined,
      response: new Response(null, {
        status: 200,
        headers: { "set-cookie": "clearpath_session=server-only-token; HttpOnly; SameSite=Lax" },
      }),
    });

    const response = await POST(
      new Request("http://localhost/api/auth/login", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          email: "person@example.com",
          password: "secret",
          stay_signed_in: false,
        }),
      }),
    );

    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ nextStep: "dashboard" });
    expect(response.headers.get("set-cookie")).toContain("HttpOnly");
    expect(response.headers.get("cache-control")).toBe("no-store");
    expect(apiPost).toHaveBeenCalledWith("/v1/auth/login", {
      body: {
        email: "person@example.com",
        password: "secret",
        stay_signed_in: false,
      },
    });
  });

  it("rejects invalid input before contacting FastAPI", async () => {
    const response = await POST(
      new Request("http://localhost/api/auth/login", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ email: "not-an-email", password: "" }),
      }),
    );

    expect(response.status).toBe(422);
    expect(apiPost).not.toHaveBeenCalled();
  });
});
