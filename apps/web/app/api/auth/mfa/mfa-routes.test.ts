import { beforeEach, describe, expect, it, vi } from "vitest";

import { GET as getChallenge } from "./challenge/route";
import { GET as getRecovery, POST as postRecovery } from "./recovery/route";
import { POST as postVerify } from "./verify/route";

const apiGet = vi.hoisted(() => vi.fn());
const apiPost = vi.hoisted(() => vi.fn());

vi.mock("@clearpath/api-client", () => ({
  createClearPathClient: () => ({ GET: apiGet, POST: apiPost }),
}));

describe("MFA API proxies", () => {
  beforeEach(() => {
    apiGet.mockReset();
    apiPost.mockReset();
  });

  it("forwards the pending cookie and maps the challenge for the client", async () => {
    apiGet.mockResolvedValue({
      data: {
        subject_type: "household_member",
        subject_id: 9,
        email: "member@example.com",
        preferred_method: "totp",
        push_available: false,
        email_available: false,
        email_challenge_sent: false,
      },
      error: undefined,
      response: new Response(null, { status: 200 }),
    });

    const response = await getChallenge(
      new Request("http://localhost/api/auth/mfa/challenge", {
        headers: { cookie: "clearpath_session=pending-token" },
      }),
    );

    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({
      subjectType: "household_member",
      email: "member@example.com",
      preferredMethod: "totp",
      pushAvailable: false,
      emailAvailable: false,
      emailChallengeSent: false,
    });
    expect(apiGet).toHaveBeenCalledWith("/v1/auth/mfa/challenge", {
      headers: { cookie: "clearpath_session=pending-token" },
      params: { query: { email_challenge_token: undefined } },
    });
  });

  it("keeps the full token out of JSON and forwards the completed session cookie", async () => {
    apiPost.mockResolvedValue({
      data: {
        access_token: "full-session-token",
        next_step: "dashboard",
      },
      error: undefined,
      response: new Response(null, {
        status: 200,
        headers: { "set-cookie": "clearpath_session=full-session-token; HttpOnly; SameSite=Lax" },
      }),
    });

    const response = await postVerify(
      new Request("http://localhost/api/auth/mfa/verify", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          cookie: "clearpath_session=pending-token",
        },
        body: JSON.stringify({ method: "totp", code: "123456" }),
      }),
    );

    expect(await response.json()).toEqual({ nextStep: "dashboard" });
    expect(response.headers.get("set-cookie")).toContain("full-session-token");
    expect(apiPost).toHaveBeenCalledWith("/v1/auth/mfa/verify", {
      body: { method: "totp", code: "123456", email_challenge_token: undefined },
      headers: { cookie: "clearpath_session=pending-token" },
    });
  });

  it("keeps the email challenge in an httpOnly cookie and forwards it for verification", async () => {
    apiGet.mockResolvedValue({
      data: {
        subject_type: "user",
        subject_id: 3,
        email: "person@example.com",
        preferred_method: "email",
        push_available: false,
        email_available: true,
        email_challenge_sent: true,
        email_challenge_token: "signed-email-challenge",
      },
      error: undefined,
      response: new Response(null, { status: 200 }),
    });
    const challengeResponse = await getChallenge(
      new Request("http://localhost/api/auth/mfa/challenge", {
        headers: { cookie: "clearpath_session=pending-token" },
      }),
    );
    expect(await challengeResponse.json()).not.toHaveProperty("emailChallengeToken");
    expect(challengeResponse.headers.get("set-cookie")).toContain("HttpOnly");
    expect(challengeResponse.headers.get("set-cookie")).toContain("signed-email-challenge");

    apiPost.mockResolvedValue({
      data: { access_token: "full-session-token", next_step: "dashboard" },
      error: undefined,
      response: new Response(null, {
        status: 200,
        headers: { "set-cookie": "clearpath_session=full-session-token; HttpOnly" },
      }),
    });
    await postVerify(
      new Request("http://localhost/api/auth/mfa/verify", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          cookie: "clearpath_session=pending-token; clearpath_mfa_email_challenge=signed-email-challenge",
        },
        body: JSON.stringify({ method: "email", email_code: "654321" }),
      }),
    );
    expect(apiPost).toHaveBeenLastCalledWith("/v1/auth/mfa/verify", {
      body: {
        method: "email",
        email_code: "654321",
        email_challenge_token: "signed-email-challenge",
      },
      headers: {
        cookie: "clearpath_session=pending-token; clearpath_mfa_email_challenge=signed-email-challenge",
      },
    });
  });

  it("checks recovery availability and consumes a recovery code through the pending session", async () => {
    apiGet.mockResolvedValue({
      data: { available: true },
      error: undefined,
      response: new Response(null, { status: 200 }),
    });

    const challengeResponse = await getRecovery(
      new Request("http://localhost/api/auth/mfa/recovery", {
        headers: { cookie: "clearpath_session=pending-token" },
      }),
    );
    expect(await challengeResponse.json()).toEqual({ available: true });

    apiPost.mockResolvedValue({
      data: { access_token: "full-session-token", next_step: "onboarding" },
      error: undefined,
      response: new Response(null, {
        status: 200,
        headers: { "set-cookie": "clearpath_session=full-session-token; HttpOnly" },
      }),
    });
    const response = await postRecovery(
      new Request("http://localhost/api/auth/mfa/recovery", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          cookie: "clearpath_session=pending-token",
        },
        body: JSON.stringify({ recovery_code: "ABCD-EFGH-IJKL" }),
      }),
    );

    expect(await response.json()).toEqual({ nextStep: "onboarding" });
    expect(apiPost).toHaveBeenCalledWith("/v1/auth/mfa/recovery", {
      body: { recovery_code: "ABCD-EFGH-IJKL" },
      headers: { cookie: "clearpath_session=pending-token" },
    });
  });

  it("rejects an empty verification code before contacting FastAPI", async () => {
    const response = await postVerify(
      new Request("http://localhost/api/auth/mfa/verify", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ method: "totp", code: "" }),
      }),
    );

    expect(response.status).toBe(422);
    expect(apiPost).not.toHaveBeenCalled();
  });
});
