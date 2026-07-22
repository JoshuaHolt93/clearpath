import type { HelpView } from "@clearpath/validation";
import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { clearNavigationSession } from "../authenticated-shell";
import { HelpWorkspace } from "./help-workspace";

const replace = vi.fn();
vi.mock("next/navigation", () => ({ usePathname: () => "/help", useRouter: () => ({ push: vi.fn(), replace, refresh: vi.fn() }) }));
const view: HelpView = { session: { ownerUserId: 1, householdName: "Holt Household", selectedPlan: "basic", billingStatus: "plan_selected", planDisplayName: "Plus", primaryAccountHolder: true, subject: { id: 1, subjectType: "user", email: "owner@example.com", displayName: "Owner", firstName: "Owner", avatarInitial: "O", householdRole: null }, featureAccess: [] } };
describe("HelpWorkspace", () => {
  beforeEach(() => { vi.restoreAllMocks(); replace.mockReset(); });
  afterEach(() => clearNavigationSession());
  it("renders the canonical help flow and all page guides", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify(view), { status: 200 }));
    render(<HelpWorkspace selectedTopic="transactions" />);
    expect(await screen.findByRole("heading", { name: "Help" })).toBeDefined();
    expect(screen.getByText("11 Guides")).toBeDefined();
    expect(screen.getByRole("heading", { name: "Review Transactions" })).toBeDefined();
    expect(screen.getByRole("link", { name: "Replay Today Tutorial" }).getAttribute("href")).toBe("/dashboard?welcome=1&tutorial=today");
  });
  it("sends signed-out visitors to login", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ message: "Sign in." }), { status: 401 }));
    render(<HelpWorkspace selectedTopic="" />);
    await vi.waitFor(() => expect(replace).toHaveBeenCalledWith("/login?next=/help"));
  });
});
