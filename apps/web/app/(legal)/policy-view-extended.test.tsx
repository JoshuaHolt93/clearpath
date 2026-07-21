import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { PolicyView } from "./policy-view";
import {
  ETHICS_POLICY,
  INFORMATION_REQUIREMENTS_POLICY,
  MONEY_TRANSMISSION_POLICY,
  PCI_SAQ_A_POLICY,
} from "@/lib/legal-content-policies";

vi.mock("next/navigation", () => ({ usePathname: () => "/ethics", useRouter: () => ({ push: vi.fn() }) }));

describe("PolicyView (extended policies)", () => {
  it("renders the ethics policy with all commitments", () => {
    render(<PolicyView policy={ETHICS_POLICY} />);
    expect(screen.getByRole("heading", { level: 1, name: "ClearPath Ethics, Terms, and Privacy Policy" })).toBeDefined();
    expect(screen.getByRole("heading", { level: 2, name: "Conflicts Of Interest" })).toBeDefined();
    expect(screen.getByRole("heading", { level: 2, name: "Reporting Concerns" })).toBeDefined();
  });

  it("renders owner, review cadence, and section summaries for the info-requirements policy", () => {
    render(<PolicyView policy={INFORMATION_REQUIREMENTS_POLICY} />);
    expect(screen.getByText("Owner: ClearPath Finance Security Owner")).toBeDefined();
    const identity = screen.getByRole("heading", { level: 2, name: "Identity And Access Information" }).closest("section")!;
    expect(within(identity).getByText(/needed to authenticate users/i)).toBeDefined();
  });

  it("renders the PCI scope and money-transmission launch-blocker note", () => {
    render(<PolicyView policy={PCI_SAQ_A_POLICY} />);
    expect(screen.getByText(/PCI SAQ-A scope/i)).toBeDefined();

    render(<PolicyView policy={MONEY_TRANSMISSION_POLICY} />);
    expect(screen.getByText(/Launch blocker:/i)).toBeDefined();
    expect(screen.getByRole("heading", { level: 2, name: /Future Or Prohibited Capabilities/i })).toBeDefined();
  });
});
