import type { BillingView } from "@clearpath/validation";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { BillingWorkspace } from "./billing-workspace";

vi.mock("next/navigation", () => ({ usePathname: () => "/billing", useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }) }));

function plan(key: string, name: string, price: string) {
  return { key, name, amountCents: 699, currency: "USD", billingInterval: "month", priceDisplay: price, intervalDisplay: "Month", trialPeriodDays: 0, features: [`${name} feature`], priceConfigured: false };
}

function view(overrides: Partial<BillingView> = {}): BillingView {
  return {
    session: {
      ownerUserId: 1,
      householdName: "Holt Household",
      selectedPlan: "basic",
      billingStatus: "plan_selected",
      planDisplayName: "Plus",
      primaryAccountHolder: true,
      subject: { id: 1, subjectType: "user", email: "owner@example.com", displayName: "Owner", firstName: "Owner", avatarInitial: "O", householdRole: null },
      featureAccess: [],
    },
    plans: [plan("at_cost", "ClearPath Basic", "$2.99"), plan("basic", "ClearPath Plus", "$6.99"), plan("premium", "ClearPath Premier", "$11.99")],
    billingConfig: { enabled: false },
    pricingPolicy: { price_display: "$12.00" },
    freeTierSignupsEnabled: false,
    upgradeTutorials: { basic: [], premium: [] },
    canManageBilling: true,
    userState: { selectedPlan: "basic", billingStatus: "plan_selected", hasStripeCustomer: false, hasStripeSubscription: false, stripeCurrentPeriodEnd: null, billingPriceId: null, config: { enabled: false } },
    feedbackOptions: { reasons: [["too_expensive", "Too expensive"]], featureExpectationReasons: [], brokenFeatures: [] },
    ...overrides,
  };
}

function json(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), { status, headers: { "content-type": "application/json" } });
}

describe("BillingWorkspace", () => {
  beforeEach(() => { vi.restoreAllMocks(); });

  it("renders plan cards with the current plan flagged and context-aware labels", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(json(view()));
    render(<BillingWorkspace />);
    expect(await screen.findByText("ClearPath Plus")).toBeDefined();
    expect(screen.getByText("$2.99")).toBeDefined();
    // Current plan (basic) shows a disabled "Current Plan" button; premium is an upgrade.
    const premium = screen.getByText("ClearPath Premier").closest("form")!;
    expect(within(premium).getByRole("button", { name: "Upgrade to Premier" })).toBeDefined();
    expect(screen.getByText("Billing is not enabled in this environment, so a selected plan is saved without opening Stripe Checkout.")).toBeDefined();
  });

  it("selects a plan locally when billing is disabled", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) =>
      init?.method === "POST" && String(input).includes("/api/billing/plan-selection")
        ? json({ selectedPlan: "premium", planName: "ClearPath Premier", alreadySelected: false, checkoutUrl: null })
        : json(view()),
    );
    render(<BillingWorkspace />);
    const premium = (await screen.findByText("ClearPath Premier")).closest("form")!;
    fireEvent.click(within(premium).getByRole("button", { name: "Upgrade to Premier" }));
    expect(await screen.findByText("ClearPath Premier selected.")).toBeDefined();
    const call = fetchMock.mock.calls.find(([input]) => String(input).includes("/api/billing/plan-selection"));
    expect(JSON.parse(String(call?.[1]?.body))).toMatchObject({ plan: "premium" });
  });

  it("hands off to Stripe when a checkout url is returned", async () => {
    const assign = vi.fn();
    vi.stubGlobal("location", { assign } as unknown as Location);
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) =>
      init?.method === "POST" && String(input).includes("/api/billing/plan-selection")
        ? json({ selectedPlan: "premium", planName: "ClearPath Premier", alreadySelected: false, checkoutUrl: "https://checkout.stripe.test/session" })
        : json(view({ billingConfig: { enabled: true } })),
    );
    render(<BillingWorkspace />);
    const premium = (await screen.findByText("ClearPath Premier")).closest("form")!;
    fireEvent.click(within(premium).getByRole("button", { name: "Upgrade to Premier" }));
    await vi.waitFor(() => expect(assign).toHaveBeenCalledWith("https://checkout.stripe.test/session"));
    vi.unstubAllGlobals();
  });

  it("shows manage actions and cancellation form when a Stripe subscription exists", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      if (init?.method === "POST" && String(input).includes("/api/billing/cancel")) {
        return json({ feedbackSaved: true, portalUrl: null, message: "Your feedback was saved, but no Stripe customer is connected to this account yet." });
      }
      return json(view({ userState: { selectedPlan: "premium", billingStatus: "active", hasStripeCustomer: true, hasStripeSubscription: true, stripeCurrentPeriodEnd: null, billingPriceId: "price_x", config: { enabled: true } }, billingConfig: { enabled: true } }));
    });
    render(<BillingWorkspace />);
    expect(await screen.findByRole("heading", { name: "Manage Subscription" })).toBeDefined();
    fireEvent.click(screen.getByRole("button", { name: "Cancel Subscription" }));
    const cancelForm = screen.getByRole("button", { name: "Continue To Stripe Cancellation" }).closest("form")!;
    fireEvent.change(within(cancelForm).getByLabelText("Reason (Optional)"), { target: { value: "too_expensive" } });
    fireEvent.click(within(cancelForm).getByRole("button", { name: "Continue To Stripe Cancellation" }));
    expect(await screen.findByText(/Your feedback was saved/)).toBeDefined();
    const call = fetchMock.mock.calls.find(([input]) => String(input).includes("/api/billing/cancel"));
    expect(JSON.parse(String(call?.[1]?.body))).toMatchObject({ reason: "too_expensive" });
  });

  it("keeps shared sessions read-only with no selection controls", async () => {
    const base = view();
    vi.spyOn(globalThis, "fetch").mockResolvedValue(json(view({
      session: { ...base.session, primaryAccountHolder: false, subject: { ...base.session.subject, subjectType: "household_member", householdRole: "viewer" } },
      canManageBilling: false,
      userState: null,
      feedbackOptions: null,
    })));
    render(<BillingWorkspace />);
    expect(await screen.findByText("Billing is managed by the primary account holder. You can review the available plans below.")).toBeDefined();
    expect(screen.queryByRole("button", { name: "Upgrade to Premier" })).toBeNull();
    expect(screen.queryByRole("heading", { name: "Manage Subscription" })).toBeNull();
  });
});
