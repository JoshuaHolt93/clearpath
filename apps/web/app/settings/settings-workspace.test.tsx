import type { SettingsView } from "@clearpath/validation";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SettingsWorkspace } from "./settings-workspace";

vi.mock("next/navigation", () => ({ usePathname: () => "/settings", useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }) }));

function view(overrides: Partial<SettingsView> = {}): SettingsView {
  return {
    session: {
      ownerUserId: 1,
      householdName: "Holt Household",
      selectedPlan: "premium",
      billingStatus: "active",
      planDisplayName: "Premier",
      primaryAccountHolder: true,
      subject: { id: 1, subjectType: "user", email: "owner@example.com", displayName: "Owner", firstName: "Owner", avatarInitial: "O", householdRole: null },
      featureAccess: [],
    },
    email: "owner@example.com",
    displayName: "Owner",
    householdName: "Holt Household",
    rulesCount: 3,
    categoryRows: [{ id: 10, name: "Groceries", kind: "expense", monthlyTarget: 600, canManage: true, usage: { transactions: 4 } }],
    plaidStatus: { configured: true, ready: true },
    pushMfa: { available: false },
    mfaPreferredMethod: "totp",
    mfaPushEnabled: false,
    billingStatus: { enabled: false },
    feedbackOptions: { reasons: [["other", "Other"]], featureExpectationReasons: [], brokenFeatures: [] },
    householdRoleOptions: { editor: "Can Edit", viewer: "View Only" },
    householdMembers: [{ id: 7, email: "partner@example.com", displayName: "Partner", role: "viewer", status: "active", acceptedAt: "2026-07-01T00:00:00" }],
    pendingHouseholdInvites: [{ id: 3, email: "cousin@example.com", role: "editor", status: "pending", expiresAt: null }],
    canManageHouseholdAccess: true,
    householdAccessIsShared: false,
    ethicsAcknowledgedAt: null,
    ethicsPolicyVersion: null,
    accountDeleteConfirmation: "DELETE MY ACCOUNT",
    accountDeleteBillingBlocked: false,
    ...overrides,
  };
}

function json(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), { status, headers: { "content-type": "application/json" } });
}

describe("SettingsWorkspace", () => {
  beforeEach(() => { vi.restoreAllMocks(); });

  it("renders household, security, shared access, and danger sections for the primary holder", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(json(view()));
    render(<SettingsWorkspace />);
    expect(await screen.findByRole("heading", { name: "Household" })).toBeDefined();
    expect(screen.getByLabelText("Household Name").getAttribute("value")).toBe("Holt Household");
    expect(screen.getByRole("heading", { name: "Security" })).toBeDefined();
    expect(screen.getByText("Duo Push approval (not configured)")).toBeDefined();
    expect(screen.getByText("partner@example.com (partner@example.com)".replace("partner@example.com (", "Partner ("))).toBeDefined();
    expect(screen.getByText(/cousin@example.com/)).toBeDefined();
    expect(screen.getByRole("heading", { name: "Delete Account" })).toBeDefined();
    expect(screen.getByRole("button", { name: "Acknowledge Policy" })).toBeDefined();
  });

  it("submits a password change and surfaces the API error text", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) =>
      init?.method === "POST" && String(input).includes("/api/settings/account")
        ? json({ message: "Current password was incorrect." }, 422)
        : json(view()),
    );
    render(<SettingsWorkspace />);
    const security = (await screen.findByRole("heading", { name: "Security" })).closest("section")!;
    const form = within(security).getByRole("button", { name: "Update Password" }).closest("form")!;
    fireEvent.change(within(form).getByLabelText("Current Password"), { target: { value: "wrong" } });
    fireEvent.change(within(form).getByLabelText("New Password"), { target: { value: "NewHorse2@" } });
    fireEvent.change(within(form).getByLabelText("Confirm New Password"), { target: { value: "NewHorse2@" } });
    fireEvent.click(within(form).getByRole("button", { name: "Update Password" }));
    expect(await screen.findByText("Current password was incorrect.")).toBeDefined();
    const call = fetchMock.mock.calls.find(([input]) => String(input).includes("/api/settings/account"));
    expect(JSON.parse(String(call?.[1]?.body))).toMatchObject({ action: "password", currentPassword: "wrong" });
  });

  it("creates an invite and shows the fallback link when email delivery is unavailable", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) =>
      init?.method === "POST" && String(input).includes("/api/settings/invites")
        ? json({ invite: { id: 9, email: "friend@example.com", role: "viewer", status: "pending", expiresAt: null }, emailSent: false, fallbackInviteUrl: "http://web.local/household/invite/tok123", deliveryReason: "not_configured" }, 201)
        : json(view()),
    );
    render(<SettingsWorkspace />);
    const shared = (await screen.findByRole("heading", { name: "Shared Household Access" })).closest("section")!;
    fireEvent.change(within(shared).getByLabelText("Invite Email"), { target: { value: "friend@example.com" } });
    fireEvent.click(within(shared).getByRole("button", { name: "Send Invite" }));
    expect(await screen.findByText(/Fallback invite link:/)).toBeDefined();
    expect(screen.getByText("http://web.local/household/invite/tok123")).toBeDefined();
    const call = fetchMock.mock.calls.find(([input]) => String(input).includes("/api/settings/invites"));
    expect(JSON.parse(String(call?.[1]?.body))).toMatchObject({ inviteEmail: "friend@example.com", inviteRole: "editor" });
  });

  it("hides primary-only sections for shared household sessions", async () => {
    const base = view();
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      json(
        view({
          session: { ...base.session, primaryAccountHolder: false, subject: { ...base.session.subject, subjectType: "household_member", householdRole: "viewer" } },
          canManageHouseholdAccess: false,
          householdAccessIsShared: true,
        }),
      ),
    );
    render(<SettingsWorkspace />);
    expect(await screen.findByText(/the primary account holder manages household settings/)).toBeDefined();
    expect(screen.queryByRole("heading", { name: "Security" })).toBeNull();
    expect(screen.queryByRole("heading", { name: "Shared Household Access" })).toBeNull();
    expect(screen.queryByRole("heading", { name: "Delete Account" })).toBeNull();
  });
});
