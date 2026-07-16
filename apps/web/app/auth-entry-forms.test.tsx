import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ForgotPasswordForm } from "./forgot-password/forgot-password-form";
import { RegisterForm } from "./register/register-form";
import { ResetPasswordForm } from "./reset-password/[token]/reset-password-form";

const navigation = vi.hoisted(() => ({ push: vi.fn(), refresh: vi.fn() }));

vi.mock("next/navigation", () => ({ useRouter: () => navigation }));

describe("registration and password-reset forms", () => {
  beforeEach(() => {
    navigation.push.mockReset();
    navigation.refresh.mockReset();
    vi.restoreAllMocks();
  });

  it("submits a normalized registration and follows the auth next step", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ nextStep: "mfa_setup" }), { status: 201, headers: { "content-type": "application/json" } }),
    );
    render(<RegisterForm />);
    fireEvent.change(screen.getByLabelText("Your Name"), { target: { value: "  Jordan Parker " } });
    fireEvent.change(screen.getByLabelText("Household Name"), { target: { value: "  Parker Home " } });
    fireEvent.change(screen.getByLabelText("Email Address"), { target: { value: "  JORDAN@example.com " } });
    fireEvent.change(screen.getByLabelText("Password", { selector: "input" }), { target: { value: "CorrectHorse1!" } });
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: "Create Account" }));

    await waitFor(() => expect(navigation.push).toHaveBeenCalledWith("/mfa/setup"));
    expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))).toEqual({
      display_name: "Jordan Parker",
      household_name: "Parker Home",
      email: "jordan@example.com",
      password: "CorrectHorse1!",
      policy_acknowledgement: true,
    });
  });

  it("requires policy acceptance before registration reaches the server", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    render(<RegisterForm />);
    fireEvent.change(screen.getByLabelText("Your Name"), { target: { value: "Jordan" } });
    fireEvent.change(screen.getByLabelText("Email Address"), { target: { value: "jordan@example.com" } });
    fireEvent.change(screen.getByLabelText("Password", { selector: "input" }), { target: { value: "CorrectHorse1!" } });
    fireEvent.click(screen.getByRole("button", { name: "Create Account" }));
    expect((await screen.findByRole("alert")).textContent).toContain("accept the ClearPath policies");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("keeps the generic reset message and shows the local link when supplied", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({
        message: "If an account exists for that email, a password reset link has been sent.",
        resetUrl: "/reset-password/signed-token",
      }), { status: 200, headers: { "content-type": "application/json" } }),
    );
    render(<ForgotPasswordForm />);
    fireEvent.change(screen.getByLabelText("Email Address"), { target: { value: "person@example.com" } });
    fireEvent.click(screen.getByRole("button", { name: "Send Reset Link" }));
    expect((await screen.findByRole("status")).textContent).toContain("If an account exists");
    expect(screen.getByRole("link", { name: "Reset Password" }).getAttribute("href")).toBe("/reset-password/signed-token");
  });

  it("validates the token, resets the password, and returns to sign in", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify({ valid: true, email: "person@example.com" }), { status: 200, headers: { "content-type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ok: true }), { status: 200, headers: { "content-type": "application/json" } }));
    render(<ResetPasswordForm token="signed-token" />);
    const password = await screen.findByLabelText("New Password", { selector: "input" });
    fireEvent.change(password, { target: { value: "NewCorrectHorse2!" } });
    fireEvent.change(screen.getByLabelText("Confirm New Password", { selector: "input" }), { target: { value: "NewCorrectHorse2!" } });
    fireEvent.click(screen.getByRole("button", { name: "Reset Password" }));

    await waitFor(() => expect(navigation.push).toHaveBeenCalledWith("/login?password_reset=1"));
    expect(fetchMock.mock.calls[1]?.[0]).toBe("/api/auth/password-reset/signed-token");
    expect(JSON.parse(String(fetchMock.mock.calls[1]?.[1]?.body))).toEqual({
      password: "NewCorrectHorse2!",
      confirm_password: "NewCorrectHorse2!",
    });
  });

  it("renders an expired-link recovery path", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ valid: false, email: null }), { status: 200, headers: { "content-type": "application/json" } }),
    );
    render(<ResetPasswordForm token="expired-token" />);
    expect((await screen.findByRole("alert")).textContent).toContain("invalid or expired");
    expect(screen.getByRole("link", { name: "Request A New Reset Link" }).getAttribute("href")).toBe("/forgot-password");
  });
});
