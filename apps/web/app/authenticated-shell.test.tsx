import type { SignedInSession } from "@clearpath/validation";
import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AuthenticatedPageFrame, clearNavigationSession } from "./authenticated-shell";

vi.mock("next/navigation", () => ({
  usePathname: () => "/transactions",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }),
}));

const session: SignedInSession = {
  ownerUserId: 1,
  householdName: "Holt Household",
  selectedPlan: "basic",
  billingStatus: "plan_selected",
  planDisplayName: "Plus",
  primaryAccountHolder: true,
  subject: {
    id: 1,
    subjectType: "user",
    email: "owner@example.com",
    displayName: "Owner",
    firstName: "Owner",
    avatarInitial: "O",
    householdRole: null,
  },
  featureAccess: [],
};

describe("AuthenticatedPageFrame", () => {
  afterEach(() => clearNavigationSession());

  it("keeps authenticated navigation visible while the next page loads", () => {
    const first = render(<AuthenticatedPageFrame session={session}><div>Transactions ready</div></AuthenticatedPageFrame>);
    first.unmount();

    render(<AuthenticatedPageFrame><div>Loading analytics...</div></AuthenticatedPageFrame>);

    expect(screen.getByRole("navigation", { name: "Primary navigation" })).toBeDefined();
    expect(screen.getByText("Loading analytics...")).toBeDefined();
  });
});
