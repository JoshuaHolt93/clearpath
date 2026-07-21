import type { ComplianceView } from "@clearpath/validation";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ComplianceWorkspace } from "./compliance-workspace";

vi.mock("next/navigation", () => ({ usePathname: () => "/compliance", useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }) }));

function session() {
  return {
    ownerUserId: 1,
    householdName: "Holt Household",
    selectedPlan: "premium",
    billingStatus: "active",
    planDisplayName: "Premier",
    primaryAccountHolder: true,
    subject: { id: 1, subjectType: "user" as const, email: "admin@example.com", displayName: "Admin", firstName: "Admin", avatarInitial: "A", householdRole: null },
    featureAccess: [],
  };
}

function view(overrides: Partial<ComplianceView> = {}): ComplianceView {
  return {
    session: session(),
    isAdmin: true,
    evaluations: [
      { id: 1, controlId: "CC4.1-HTTPS", controlName: "Production HTTPS Enforcement", status: "warn", evidence: "Testing is not enforcing production HTTPS settings.", evaluatedAt: "2026-07-18T12:00:00" },
      { id: 2, controlId: "CC4.1-CSRF", controlName: "CSRF Enforcement", status: "pass", evidence: "API sessions use bearer/httpOnly JWTs.", evaluatedAt: "2026-07-18T12:00:00" },
    ],
    controls: [{ id: "CC4.1-CSRF", name: "CSRF Enforcement", description: "Verifies CSRF protection.", ownerRole: "Engineering Owner", reviewCadence: "Every run." }],
    ...overrides,
  };
}

function json(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), { status, headers: { "content-type": "application/json" } });
}

describe("ComplianceWorkspace", () => {
  beforeEach(() => { vi.restoreAllMocks(); });

  it("renders the evaluation table and catalog for admins", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(json(view()));
    render(<ComplianceWorkspace />);
    expect(await screen.findByRole("heading", { name: "Latest Evaluations" })).toBeDefined();
    expect(screen.getByText("Production HTTPS Enforcement")).toBeDefined();
    expect(screen.getByText("Warn")).toBeDefined();
    expect(screen.getByText("Pass")).toBeDefined();
    expect(screen.getByRole("heading", { name: "Control Catalog" })).toBeDefined();
  });

  it("runs evaluations and reloads", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (_input, init) =>
      init?.method === "POST" ? json({ evaluated: 6, message: "Recorded 6 SOC2 CC4.1 control evaluation results." }) : json(view()),
    );
    render(<ComplianceWorkspace />);
    await screen.findByRole("heading", { name: "Latest Evaluations" });
    fireEvent.click(screen.getByRole("button", { name: "Run Evaluations" }));
    expect(await screen.findByText("Recorded 6 SOC2 CC4.1 control evaluation results.")).toBeDefined();
    expect(fetchMock.mock.calls.filter(([, init]) => init?.method === "POST").length).toBe(1);
  });

  it("shows an access-required notice for non-admins", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(json(view({ isAdmin: false, evaluations: [], controls: [] })));
    render(<ComplianceWorkspace />);
    expect(await screen.findByText("Administrator access is required to view compliance control evaluations.")).toBeDefined();
    expect(screen.queryByRole("button", { name: "Run Evaluations" })).toBeNull();
  });
});
