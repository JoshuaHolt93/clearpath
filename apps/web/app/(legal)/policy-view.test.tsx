import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { PolicyView } from "./policy-view";
import { PRIVACY_POLICY, TERMS_OF_SERVICE } from "@/lib/legal-content";

vi.mock("next/navigation", () => ({ usePathname: () => "/privacy", useRouter: () => ({ push: vi.fn() }) }));

describe("PolicyView", () => {
  it("renders the privacy policy title, version, and every section", () => {
    render(<PolicyView policy={PRIVACY_POLICY} />);
    expect(screen.getByRole("heading", { level: 1, name: "ClearPath Privacy Policy" })).toBeDefined();
    expect(screen.getByText(/Version 2026.05.14/)).toBeDefined();
    for (const section of PRIVACY_POLICY.sections) {
      expect(screen.getByRole("heading", { level: 2, name: section.heading })).toBeDefined();
    }
    expect(screen.getByText(/does not sell personal financial data/i)).toBeDefined();
  });

  it("renders the terms of service with the acceptable-use and liability sections", () => {
    render(<PolicyView policy={TERMS_OF_SERVICE} />);
    expect(screen.getByRole("heading", { level: 1, name: "ClearPath Terms Of Service" })).toBeDefined();
    const liability = screen.getByRole("heading", { level: 2, name: "Liability Boundaries" }).closest("section")!;
    expect(within(liability).getByText(/provided as-is and as-available/i)).toBeDefined();
  });
});
