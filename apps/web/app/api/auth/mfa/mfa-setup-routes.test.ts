import { beforeEach, describe, expect, it, vi } from "vitest";

import { POST as sendSetupEmail } from "./setup/email-code/route";
import { GET as getMobileSetup } from "./setup/mobile/[token]/route";
import { GET as getSetup, POST as postSetup } from "./setup/route";
import { GET as completePush } from "./push/callback/route";
import { POST as startPush } from "./push/start/route";

const apiGet = vi.hoisted(() => vi.fn());
const apiPost = vi.hoisted(() => vi.fn());

vi.mock("@clearpath/api-client", () => ({
  createClearPathClient: () => ({ GET: apiGet, POST: apiPost }),
}));

describe("MFA setup and push API proxies", () => {
  beforeEach(() => {
    apiGet.mockReset();
    apiPost.mockReset();
  });

  it("maps setup data without exposing the pending session token", async () => {
    apiGet.mockResolvedValue({
      data: {
        subject_type: "user",
        subject_id: 4,
        email: "setup@example.com",
        mfa_enabled: false,
        preferred_method: "totp",
        setup_key: "JBSWY3DPEHPK3PXP",
        provisioning_uri: "otpauth://totp/ClearPath?secret=JBSWY3DPEHPK3PXP",
        mobile_setup_token: "mobile-token",
        push_available: true,
        push_provider: "duo",
        push_configured: true,
        shared_access_totp_only: false,
        email_available: true,
        recovery_codes: null,
      },
      error: undefined,
      response: new Response(null, { status: 200 }),
    });

    const response = await getSetup(
      new Request("http://localhost/api/auth/mfa/setup", {
        headers: { cookie: "clearpath_session=pending-token" },
      }),
    );
    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({
      email: "setup@example.com",
      setupKey: "JBSWY3DPEHPK3PXP",
      mobileSetupToken: "mobile-token",
      pushAvailable: true,
      emailAvailable: true,
    });
  });

  it("stores an email challenge httpOnly and uses it to complete setup", async () => {
    apiPost.mockResolvedValueOnce({
      data: { sent: true, reason: null, challenge_token: "setup-email-token" },
      error: undefined,
      response: new Response(null, { status: 200 }),
    });
    const emailResponse = await sendSetupEmail(
      new Request("http://localhost/api/auth/mfa/setup/email-code", {
        method: "POST",
        headers: { cookie: "clearpath_session=pending-token" },
      }),
    );
    expect(await emailResponse.json()).toEqual({ sent: true, reason: null });
    expect(emailResponse.headers.get("set-cookie")).toContain("setup-email-token");
    expect(emailResponse.headers.get("set-cookie")).toContain("HttpOnly");

    apiPost.mockResolvedValueOnce({
      data: {
        access_token: "full-session-token",
        next_step: "select_plan",
        recovery_codes: ["AAAA-BBBB-CCCC"],
      },
      error: undefined,
      response: new Response(null, {
        status: 200,
        headers: { "set-cookie": "clearpath_session=full-session-token; HttpOnly" },
      }),
    });
    const setupResponse = await postSetup(
      new Request("http://localhost/api/auth/mfa/setup", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          cookie: "clearpath_session=pending-token; clearpath_mfa_email_challenge=setup-email-token",
        },
        body: JSON.stringify({ action: "confirm_email_code", email_code: "123456" }),
      }),
    );
    expect(await setupResponse.json()).toEqual({
      nextStep: "select_plan",
      recoveryCodes: ["AAAA-BBBB-CCCC"],
    });
    expect(setupResponse.headers.get("set-cookie")).toContain("full-session-token");
    expect(apiPost).toHaveBeenLastCalledWith("/v1/auth/mfa/setup", {
      body: {
        action: "confirm_email_code",
        email_code: "123456",
        mfa_push_opt_in: false,
        email_challenge_token: "setup-email-token",
      },
      headers: {
        cookie: "clearpath_session=pending-token; clearpath_mfa_email_challenge=setup-email-token",
      },
    });
  });

  it("proxies the public mobile handoff token", async () => {
    apiGet.mockResolvedValue({
      data: {
        provisioning_uri: "otpauth://totp/ClearPath?secret=KEY",
        expired: false,
        email: "mobile@example.com",
        subject_type: "user",
      },
      error: undefined,
      response: new Response(null, { status: 200 }),
    });
    const response = await getMobileSetup(
      new Request("http://localhost/api/auth/mfa/setup/mobile/mobile-token"),
      { params: Promise.resolve({ token: "mobile-token" }) },
    );
    expect(response.status).toBe(200);
    expect((await response.json()).provisioningUri).toContain("otpauth://");
    expect(apiGet).toHaveBeenCalledWith("/v1/auth/mfa/setup/mobile/{token}", {
      params: { path: { token: "mobile-token" } },
    });
  });

  it("starts Duo and promotes the callback session without exposing its token", async () => {
    apiPost.mockResolvedValue({
      data: {
        push_available: true,
        fallback: "totp",
        authorization_url: "https://duo.example.test/prompt",
        reason: null,
      },
      error: undefined,
      response: new Response(null, { status: 200 }),
    });
    const startResponse = await startPush(
      new Request("http://localhost/api/auth/mfa/push/start", {
        method: "POST",
        headers: { cookie: "clearpath_session=pending-token" },
      }),
    );
    expect(await startResponse.json()).toMatchObject({
      pushAvailable: true,
      authorizationUrl: "https://duo.example.test/prompt",
    });

    apiGet.mockResolvedValue({
      data: { access_token: "full-session-token", next_step: "dashboard" },
      error: undefined,
      response: new Response(null, {
        status: 200,
        headers: { "set-cookie": "clearpath_session=full-session-token; HttpOnly" },
      }),
    });
    const callbackResponse = await completePush(
      new Request("http://localhost/api/auth/mfa/push/callback?state=signed&duo_code=approved", {
        headers: { cookie: "clearpath_session=pending-token" },
      }),
    );
    expect(await callbackResponse.json()).toEqual({ nextStep: "dashboard" });
    expect(callbackResponse.headers.get("set-cookie")).toContain("full-session-token");
    expect(apiGet).toHaveBeenCalledWith("/v1/auth/mfa/push/callback", {
      headers: { cookie: "clearpath_session=pending-token" },
      params: { query: { state: "signed", duo_code: "approved" } },
    });
  });
});
