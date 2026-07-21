import type { FeedbackView } from "@clearpath/validation";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { FeedbackWorkspace } from "./feedback-workspace";

vi.mock("next/navigation", () => ({ usePathname: () => "/feedback", useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }) }));

function view(): FeedbackView {
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
    options: {
      reasons: [["feature_expectations", "Feature expectations"], ["broken", "Something is not working"], ["other", "Other"]],
      featureExpectationReasons: [["missing_desired_features", "Features I wish existed"]],
      brokenFeatures: [["dashboard", "Dashboard"], ["transactions", "Transactions"]],
    },
  };
}

function json(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), { status, headers: { "content-type": "application/json" } });
}

describe("FeedbackWorkspace", () => {
  beforeEach(() => { vi.restoreAllMocks(); });

  it("reveals the broken-features checkboxes only when that reason is selected", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(json(view()));
    render(<FeedbackWorkspace />);
    await screen.findByText("Something is not working");
    expect(screen.queryByText("Which features were not working?")).toBeNull();
    fireEvent.click(screen.getByLabelText("Something is not working"));
    expect(screen.getByText("Which features were not working?")).toBeDefined();
    expect(screen.getByLabelText("Dashboard")).toBeDefined();
  });

  it("submits the selected reason, broken features, and description", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (_input, init) =>
      init?.method === "POST" ? json({ saved: true, message: "Thanks for the feedback. It has been saved for product review." }, 201) : json(view()),
    );
    render(<FeedbackWorkspace />);
    await screen.findByText("Something is not working");
    fireEvent.click(screen.getByLabelText("Something is not working"));
    fireEvent.click(screen.getByLabelText("Dashboard"));
    fireEvent.change(screen.getByLabelText("Optional Description"), { target: { value: "Widget failed to load." } });
    fireEvent.click(screen.getByRole("button", { name: "Send Feedback" }));
    expect(await screen.findByText("Thanks for the feedback. It has been saved for product review.")).toBeDefined();
    const call = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
    expect(JSON.parse(String(call?.[1]?.body))).toMatchObject({ reason: "broken", brokenFeatures: ["dashboard"], description: "Widget failed to load." });
  });
});
