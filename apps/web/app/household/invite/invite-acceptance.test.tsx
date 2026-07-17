import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { InviteAcceptancePanel } from "./[token]/invite-acceptance-panel";

const navigation = vi.hoisted(() => ({ push: vi.fn(), refresh: vi.fn() }));

vi.mock("next/navigation", () => ({ useRouter: () => navigation }));

describe("InviteAcceptancePanel", () => {
  beforeEach(() => {
    navigation.push.mockReset();
    navigation.refresh.mockReset();
    vi.restoreAllMocks();
  });

  it("renders canonical invitation details and creates the shared pending session", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify({
        valid: true,
        email: "shared@example.com",
        householdName: "Parker Household",
        role: "viewer",
      }), { status: 200, headers: { "content-type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ nextStep: "mfa_setup" }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }));
    render(<InviteAcceptancePanel token="invite-token" />);

    expect(await screen.findByRole("heading", { name: "Join Parker Household" })).toBeDefined();
    expect((screen.getByLabelText("Invite Email") as HTMLInputElement).value).toBe("shared@example.com");
    expect((screen.getByLabelText("Permission") as HTMLInputElement).value).toBe("View Only");
    fireEvent.change(screen.getByLabelText("Your Name"), { target: { value: "  Taylor Parker " } });
    fireEvent.change(screen.getByLabelText("Password", { selector: "input" }), { target: { value: "SharedVault123!" } });
    fireEvent.change(screen.getByLabelText("Confirm Password", { selector: "input" }), { target: { value: "SharedVault123!" } });
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: "Accept Invite" }));

    await waitFor(() => expect(navigation.push).toHaveBeenCalledWith("/mfa/setup"));
    expect(fetchMock.mock.calls[1]?.[0]).toBe("/api/household-invites/invite-token");
    expect(JSON.parse(String(fetchMock.mock.calls[1]?.[1]?.body))).toEqual({
      display_name: "Taylor Parker",
      password: "SharedVault123!",
      confirm_password: "SharedVault123!",
      policy_acknowledgement: true,
    });
  });

  it("renders the expired or used invitation state", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({
      valid: false,
      email: null,
      householdName: null,
      role: null,
    }), { status: 200, headers: { "content-type": "application/json" } }));
    render(<InviteAcceptancePanel token="used-token" />);
    expect((await screen.findByRole("alert")).textContent).toContain("expired or has already been used");
    expect(screen.getByRole("link", { name: "Back To Sign In" }).getAttribute("href")).toBe("/login");
  });

  it("requires policy acceptance before posting", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({
      valid: true,
      email: "shared@example.com",
      householdName: "Parker Household",
      role: "editor",
    }), { status: 200, headers: { "content-type": "application/json" } }));
    render(<InviteAcceptancePanel token="invite-token" />);
    await screen.findByRole("heading", { name: "Join Parker Household" });
    fireEvent.change(screen.getByLabelText("Your Name"), { target: { value: "Taylor" } });
    fireEvent.change(screen.getByLabelText("Password", { selector: "input" }), { target: { value: "SharedVault123!" } });
    fireEvent.change(screen.getByLabelText("Confirm Password", { selector: "input" }), { target: { value: "SharedVault123!" } });
    fireEvent.click(screen.getByRole("button", { name: "Accept Invite" }));
    expect((await screen.findByRole("alert")).textContent).toContain("Please accept the ClearPath Terms");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
