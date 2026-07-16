import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { MfaRecoveryPanel } from "./recovery/mfa-recovery-panel";
import { MfaVerifyPanel } from "./verify/mfa-verify-panel";

const navigation = vi.hoisted(() => ({
  push: vi.fn(),
  refresh: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => navigation,
}));

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("pending MFA panels", () => {
  beforeEach(() => {
    navigation.push.mockReset();
    navigation.refresh.mockReset();
    vi.restoreAllMocks();
  });

  it("loads the authenticator challenge and completes verification", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        jsonResponse({
          subjectType: "user",
          email: "person@example.com",
          preferredMethod: "totp",
          pushAvailable: false,
          emailAvailable: false,
          emailChallengeSent: false,
        }),
      )
      .mockResolvedValueOnce(jsonResponse({ nextStep: "dashboard" }));

    render(<MfaVerifyPanel />);
    const code = await screen.findByLabelText("6-Digit Authentication Code");
    fireEvent.change(code, { target: { value: "123456" } });
    fireEvent.click(screen.getByRole("button", { name: "Verify And Continue" }));

    await waitFor(() => expect(navigation.push).toHaveBeenCalledWith("/dashboard"));
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/auth/mfa/challenge");
    expect(fetchMock.mock.calls[1]?.[0]).toBe("/api/auth/mfa/verify");
    expect(JSON.parse(String(fetchMock.mock.calls[1]?.[1]?.body))).toEqual({
      method: "totp",
      code: "123456",
    });
    expect(navigation.refresh).toHaveBeenCalledTimes(1);
  });

  it("shows the Flask fallback when an account's preferred email method is unavailable", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({
        subjectType: "user",
        email: "person@example.com",
        preferredMethod: "email",
        pushAvailable: false,
        emailAvailable: false,
        emailChallengeSent: false,
      }),
    );

    render(<MfaVerifyPanel />);

    expect(await screen.findByText(
      "Email code delivery is temporarily unavailable. Use a recovery code to continue.",
    )).toBeDefined();
    expect(screen.queryByLabelText("Email Verification Code")).toBeNull();
    expect(screen.getByRole("link", { name: "Use A Recovery Code" }).getAttribute("href")).toBe("/mfa/recovery");
  });

  it("checks availability and consumes a recovery code", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse({ available: true }))
      .mockResolvedValueOnce(jsonResponse({ nextStep: "onboarding" }));

    render(<MfaRecoveryPanel />);
    const code = await screen.findByLabelText("Recovery Code");
    fireEvent.change(code, { target: { value: "  ABCD-EFGH-IJKL  " } });
    fireEvent.click(screen.getByRole("button", { name: "Use Recovery Code" }));

    await waitFor(() => expect(navigation.push).toHaveBeenCalledWith("/onboarding"));
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/auth/mfa/recovery");
    expect(JSON.parse(String(fetchMock.mock.calls[1]?.[1]?.body))).toEqual({
      recovery_code: "ABCD-EFGH-IJKL",
    });
  });

  it("returns to sign in when the pending session has expired", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({ message: "MFA verification is required." }, 403),
    );

    render(<MfaVerifyPanel />);

    expect((await screen.findByRole("alert")).textContent).toContain("MFA verification is required.");
    expect(screen.getByRole("link", { name: "Return To Sign In" }).getAttribute("href")).toBe("/login");
  });
});
