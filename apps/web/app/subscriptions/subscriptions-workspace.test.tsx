import type { SubscriptionsView } from "@clearpath/validation";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SubscriptionsWorkspace, type SubscriptionQuery } from "./subscriptions-workspace";

const navigation = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => navigation, usePathname: () => "/subscriptions" }));

const query: SubscriptionQuery = { q: "", status: "all", sort: "priority" };

function view(overrides: Partial<SubscriptionsView> = {}): SubscriptionsView {
  return {
    session: { ownerUserId: 1, householdName: "Owner Home", selectedPlan: "premium", billingStatus: "active", planDisplayName: "Premier", primaryAccountHolder: true, subject: { id: 1, subjectType: "user", email: "owner@example.com", displayName: "Owner User", firstName: "Owner", avatarInitial: "O", householdRole: null }, featureAccess: [{ feature: "subscriptions", enabled: true, hidden: false, requiredPlan: "Plus" }, { feature: "ai_coach", enabled: true, hidden: false, requiredPlan: "Premier" }] },
    subscriptions: [{ id: 7, merchantKey: "netflix", name: "Netflix", category: "Consumer Subscriptions", serviceCategory: "Streaming", amount: 18.99, monthlyAmount: 18.99, annualAmount: 227.88, cycle: "Monthly", cycleDays: 30, confidence: .95, status: "active", cancelUrl: "https://netflix.com/cancel", replaceable: true, firstSeen: "2026-05-01", lastSeen: "2026-06-30", nextChargeDate: "2026-07-30", notes: null, isManual: false, cycleIsManual: false, evidence: [{ id: 41, date: "2026-06-30", description: "NETFLIX.COM", amount: 18.99 }] }],
    summary: { activeCount: 1, reviewCount: 0, actionCount: 1, manageLinkCount: 1, monthlyTotal: 18.99, annualTotal: 227.88, potentialSavings: 18.99, averageConfidence: 95, transactionCount: 3 },
    categoryBreakdown: [{ category: "Streaming", amount: 18.99, percent: 100 }], opportunities: [{ subscriptionId: 7, reason: "Replaceable service" }], upcomingSubscriptionIds: [7], statuses: { active: "Active", review: "Review", canceling: "Canceling", canceled: "Canceled", ignored: "Ignored" }, cycles: ["Weekly", "Biweekly", "Monthly", "Quarterly", "Annual"], ...overrides,
  };
}
function json(payload: unknown, status = 200) { return new Response(JSON.stringify(payload), { status, headers: { "content-type": "application/json" } }); }

describe("SubscriptionsWorkspace", () => {
  beforeEach(() => { navigation.push.mockReset(); navigation.replace.mockReset(); navigation.refresh.mockReset(); vi.restoreAllMocks(); });

  it("loads the read-only subscription resource without an automatic scan", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(json(view()));
    render(<SubscriptionsWorkspace query={query} />);
    expect(await screen.findByText("Netflix")).toBeDefined();
    expect(screen.getByText("$18.99/mo")).toBeDefined();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledWith("/api/subscriptions", { cache: "no-store" });
  });

  it("keeps search, status, and sort as client URL state", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(json(view()));
    render(<SubscriptionsWorkspace query={query} />);
    await screen.findByText("Netflix");
    const form = screen.getByRole("searchbox", { name: "Search" }).closest("form")!;
    fireEvent.change(within(form).getByRole("searchbox", { name: "Search" }), { target: { value: "netflix" } });
    fireEvent.change(within(form).getByLabelText("Status"), { target: { value: "active" } });
    fireEvent.change(within(form).getByLabelText("Sort"), { target: { value: "amount_desc" } });
    fireEvent.submit(form);
    expect(navigation.push).toHaveBeenCalledWith("/subscriptions?q=netflix&status=active&sort=amount_desc");
  });

  it("runs detection only from the explicit scan command", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => init?.method === "POST" ? json({ syncedCount: 1 }) : json(view()));
    render(<SubscriptionsWorkspace query={query} />);
    await screen.findByText("Netflix");
    fireEvent.click(screen.getByRole("button", { name: "Add Subscription" }));
    fireEvent.click(await screen.findByRole("button", { name: "Run Scan" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    expect(fetchMock.mock.calls[1]).toEqual(["/api/subscriptions/scan", expect.objectContaining({ method: "POST" })]);
  });

  it("adds a manual subscription and closes the captured form after the async mutation", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (_input, init) => init?.method === "POST" ? json({ subscriptionId: 8 }, 201) : json(view()));
    render(<SubscriptionsWorkspace query={query} />);
    await screen.findByText("Netflix");
    fireEvent.click(screen.getByRole("button", { name: "Add Subscription" }));
    const addRegion = await screen.findByRole("region", { name: "Add Subscriptions" });
    fireEvent.change(within(addRegion).getByRole("textbox", { name: "Service" }), { target: { value: "Neighborhood Gym" } });
    fireEvent.change(within(addRegion).getByRole("textbox", { name: "Amount" }), { target: { value: "120" } });
    fireEvent.click(within(addRegion).getByRole("button", { name: "Add Subscription" }));
    expect(await screen.findByText("Subscription added.")).toBeDefined();
    await waitFor(() => expect(screen.queryByRole("region", { name: "Add Subscriptions" })).toBeNull());
    expect(JSON.parse(String(fetchMock.mock.calls[1]?.[1]?.body))).toMatchObject({ name: "Neighborhood Gym", amount: 120, cycle: "Monthly" });
  });

  it("keeps shared viewers read-only while preserving subscription details", async () => {
    const viewer = view({ session: { ...view().session, primaryAccountHolder: false, subject: { ...view().session.subject, subjectType: "household_member", householdRole: "viewer" } } });
    vi.spyOn(globalThis, "fetch").mockResolvedValue(json(viewer));
    render(<SubscriptionsWorkspace query={query} />);
    expect(await screen.findByText("Shared viewer access is read-only.")).toBeDefined();
    expect(screen.getByRole("button", { name: "Add Subscription" }).hasAttribute("disabled")).toBe(true);
    expect((screen.getByLabelText("Update Netflix cycle") as HTMLSelectElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: /Details/ }));
    expect(await screen.findByText("Detected Transaction Evidence")).toBeDefined();
    expect(screen.getByRole("button", { name: "Save Status" }).hasAttribute("disabled")).toBe(true);
  });
});
