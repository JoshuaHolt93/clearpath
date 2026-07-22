import type { PricingView } from "@clearpath/validation";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { PricingWorkspace } from "./pricing-workspace";

vi.mock("next/navigation", () => ({ usePathname: () => "/pricing", useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }) }));
const base: PricingView = { session: null, plans: [{ key: "at_cost", name: "ClearPath Basic", amountCents: 299, currency: "USD", billingInterval: "month", priceDisplay: "$2.99", intervalDisplay: "Month", trialPeriodDays: 30, features: ["Core budgeting"], priceConfigured: true }], pricingPolicy: { title: "ClearPath Billing And Pricing Policy", version: "2026.05.16", effectiveDate: "2026-05-16", cancellationTerms: "Cancel anytime.", paymentCollection: "Stripe hosts payment collection." } };
describe("PricingWorkspace", () => {
  beforeEach(() => { vi.restoreAllMocks(); });
  it("renders public plan details and account actions", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify(base), { status: 200 }));
    render(<PricingWorkspace />);
    expect(await screen.findByRole("heading", { name: "ClearPath Billing And Pricing Policy" })).toBeDefined();
    expect(screen.getByText("$2.99")).toBeDefined();
    expect(screen.getAllByRole("link", { name: "Create Account" }).length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: "PCI SAQ-A Controls" }).getAttribute("href")).toBe("/security/pci-saq-a");
  });
});
