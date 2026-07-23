import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PushCallbackPanel } from "./push/callback/push-callback-panel";
import { MfaSetupPanel } from "./setup/mfa-setup-panel";
import { MobileSetupPanel } from "./setup/mobile/[token]/mobile-setup-panel";

const navigation = vi.hoisted(() => ({
  push: vi.fn(),
  replace: vi.fn(),
  refresh: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => navigation,
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("qrcode", () => ({
  default: {
    toDataURL: vi.fn().mockResolvedValue("data:image/png;base64,setup-qr"),
  },
}));

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "content-type": "application/json" },
  });
}

const setupPayload = {
  subjectType: "user",
  email: "setup@example.com",
  mfaEnabled: false,
  preferredMethod: "totp",
  setupKey: "JBSWY3DPEHPK3PXP",
  provisioningUri: "otpauth://totp/ClearPath?secret=JBSWY3DPEHPK3PXP",
  mobileSetupToken: "mobile-token",
  pushAvailable: false,
  pushProvider: "none",
  pushConfigured: false,
  sharedAccessTotpOnly: false,
  emailAvailable: true,
};

describe("MFA setup clients", () => {
  beforeEach(() => {
    navigation.push.mockReset();
    navigation.replace.mockReset();
    navigation.refresh.mockReset();
    vi.restoreAllMocks();
  });

  it("confirms TOTP and reveals one-time recovery codes before continuing", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse(setupPayload))
      .mockResolvedValueOnce(
        jsonResponse({ nextStep: "select_plan", recoveryCodes: ["AAAA-BBBB-CCCC", "DDDD-EEEE-FFFF"] }),
      );

    render(<MfaSetupPanel />);
    const code = await screen.findByLabelText("6-Digit Authentication Code");
    expect(await screen.findByRole("img", { name: /scan to open/i })).toBeDefined();
    fireEvent.change(code, { target: { value: "123456" } });
    fireEvent.click(screen.getByRole("button", { name: "Enable MFA" }));

    expect(await screen.findByText("AAAA-BBBB-CCCC")).toBeDefined();
    expect(navigation.push).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(navigation.push).toHaveBeenCalledWith("/select-plan");
    expect(JSON.parse(String(fetchMock.mock.calls[1]?.[1]?.body))).toEqual({
      action: "verify_totp",
      code: "123456",
      mfa_push_opt_in: false,
    });
  });

  it("sends and confirms an email setup code", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse(setupPayload))
      .mockResolvedValueOnce(jsonResponse({ sent: true, reason: null }))
      .mockResolvedValueOnce(
        jsonResponse({ nextStep: "onboarding", recoveryCodes: ["AAAA-BBBB-CCCC"] }),
      );

    render(<MfaSetupPanel />);
    fireEvent.click(await screen.findByRole("button", { name: "Send Email Code" }));
    const emailCode = await screen.findByLabelText("Email Verification Code");
    fireEvent.change(emailCode, { target: { value: "654321" } });
    fireEvent.click(screen.getByRole("button", { name: "Use Email Codes For MFA" }));

    expect(await screen.findByText("AAAA-BBBB-CCCC")).toBeDefined();
    expect(fetchMock.mock.calls[1]?.[0]).toBe("/api/auth/mfa/setup/email-code");
    expect(JSON.parse(String(fetchMock.mock.calls[2]?.[1]?.body))).toEqual({
      action: "confirm_email_code",
      email_code: "654321",
      mfa_push_opt_in: false,
    });
  });

  it("renders an expired public mobile handoff without exposing a setup URI", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({ message: "MFA setup token is expired or invalid.", expired: true }, 410),
    );
    render(<MobileSetupPanel token="expired-token" />);

    expect((await screen.findByRole("alert")).textContent).toContain("expired or invalid");
    expect(screen.getByRole("link", { name: "Return To MFA Setup" }).getAttribute("href")).toBe("/mfa/setup");
    expect(screen.queryByRole("link", { name: "Open Authenticator App" })).toBeNull();
  });

  it("promotes the Duo callback and follows the validated next step", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ nextStep: "dashboard" }));
    render(<PushCallbackPanel />);

    await waitFor(() => expect(navigation.replace).toHaveBeenCalledWith("/dashboard"));
    expect(navigation.refresh).toHaveBeenCalledTimes(1);
  });
});
