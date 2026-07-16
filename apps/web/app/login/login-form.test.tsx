import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { LoginForm } from "./login-form";

const navigation = vi.hoisted(() => ({
  push: vi.fn(),
  refresh: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => navigation,
}));

describe("LoginForm", () => {
  beforeEach(() => {
    navigation.push.mockReset();
    navigation.refresh.mockReset();
    vi.restoreAllMocks();
  });

  it("submits normalized credentials and preserves the stay-signed-in choice", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ nextStep: "mfa_verify" }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );

    render(<LoginForm />);
    fireEvent.change(screen.getByLabelText("Email Address"), {
      target: { value: "  PERSON@Example.COM " },
    });
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "correct horse battery staple" },
    });
    fireEvent.click(screen.getByLabelText("Stay signed in on this device"));
    fireEvent.click(screen.getByRole("button", { name: "Sign In" }));

    await waitFor(() => expect(navigation.push).toHaveBeenCalledWith("/mfa/verify"));
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/auth/login");
    const options = fetchMock.mock.calls[0]?.[1];
    expect(JSON.parse(String(options?.body))).toEqual({
      email: "person@example.com",
      password: "correct horse battery staple",
      stay_signed_in: true,
    });
    expect(navigation.refresh).toHaveBeenCalledTimes(1);
  });

  it("toggles password visibility without submitting", () => {
    render(<LoginForm />);
    const password = screen.getByLabelText("Password");
    expect(password.getAttribute("type")).toBe("password");

    fireEvent.click(screen.getByRole("button", { name: "Show password" }));
    expect(password.getAttribute("type")).toBe("text");
    expect(screen.getByRole("button", { name: "Hide password" })).toBeDefined();
  });

  it("shows the API error and stays on the page", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ message: "Invalid email or password." }), {
        status: 401,
        headers: { "content-type": "application/json" },
      }),
    );

    render(<LoginForm />);
    fireEvent.change(screen.getByLabelText("Email Address"), {
      target: { value: "person@example.com" },
    });
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "wrong" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Sign In" }));

    expect((await screen.findByRole("alert")).textContent).toContain("Invalid email or password.");
    expect(navigation.push).not.toHaveBeenCalled();
  });
});
