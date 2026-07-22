import type { RetirementView } from "@clearpath/validation";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { RetirementWorkspace } from "./retirement-workspace";

vi.mock("next/navigation", () => ({ usePathname: () => "/retirement-plan", useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }) }));

function view(overrides: Partial<RetirementView> = {}): RetirementView {
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
    profile: {
      retirementEnabled: true,
      retirementHasEmployerPlan: true,
      retirementEmployerWithheld: false,
      retirementHasPersonalPlan: false,
      retirementMonthlyContribution: 400,
      retirementPersonalMonthlyContribution: 150,
      retirementLifestyleNotes: "Travel more",
      retirementLocationNotes: null,
      retirementHealthcareNotes: null,
      retirementIncomeNotes: null,
      retirementDebtNotes: null,
      retirementFamilyNotes: null,
    },
    retirementContribution: 550,
    accounts: [{ id: 3, name: "401k", accountType: "investment", institution: "Fidelity", currentBalance: 82000, isManual: false }],
    plaidStatus: { ready: true, sdkInstalled: true, environment: "sandbox" },
    ...overrides,
  };
}

function json(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), { status, headers: { "content-type": "application/json" } });
}

describe("RetirementWorkspace", () => {
  beforeEach(() => { vi.restoreAllMocks(); });

  it("renders the contribution figure, survey values, worksheet, and accounts", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(json(view()));
    render(<RetirementWorkspace />);
    expect(await screen.findByText("$550")).toBeDefined();
    expect((screen.getByLabelText("Employer Monthly Contribution") as HTMLInputElement).value).toBe("400");
    expect((screen.getByLabelText("Lifestyle") as HTMLTextAreaElement).value).toBe("Travel more");
    expect(screen.getByText("401k — Fidelity")).toBeDefined();
    expect(screen.getByText("$82,000")).toBeDefined();
  });

  it("submits the survey with full-form overwrite values", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (_input, init) =>
      init?.method === "PATCH" ? json(view({ retirementContribution: 700 })) : json(view()),
    );
    render(<RetirementWorkspace />);
    await screen.findByText("$550");
    const surveyForm = screen.getByRole("button", { name: "Save Retirement Plan" }).closest("form")!;
    fireEvent.change(within(surveyForm).getByLabelText("Personal Monthly Contribution"), { target: { value: "300" } });
    fireEvent.click(within(surveyForm).getByRole("button", { name: "Save Retirement Plan" }));
    expect(await screen.findByText("Retirement plan updated.")).toBeDefined();
    const call = fetchMock.mock.calls.find(([, init]) => init?.method === "PATCH");
    expect(JSON.parse(String(call?.[1]?.body))).toMatchObject({ section: "survey", retirementEnabled: true, retirementPersonalMonthlyContribution: 300 });
  });

  it("saves worksheet notes through the worksheet section", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (_input, init) =>
      init?.method === "PATCH" ? json(view()) : json(view()),
    );
    render(<RetirementWorkspace />);
    await screen.findByText("$550");
    const worksheetForm = screen.getByRole("button", { name: "Save Worksheet" }).closest("form")!;
    fireEvent.change(within(worksheetForm).getByLabelText("Healthcare"), { target: { value: "Medicare at 65" } });
    fireEvent.click(within(worksheetForm).getByRole("button", { name: "Save Worksheet" }));
    expect(await screen.findByText("Retirement worksheet saved.")).toBeDefined();
    const call = fetchMock.mock.calls.find(([, init]) => init?.method === "PATCH");
    expect(JSON.parse(String(call?.[1]?.body))).toMatchObject({ section: "worksheet", retirementHealthcareNotes: "Medicare at 65" });
  });

  it("disables editing for shared viewers", async () => {
    const base = view();
    vi.spyOn(globalThis, "fetch").mockResolvedValue(json(view({
      session: { ...base.session, primaryAccountHolder: false, subject: { ...base.session.subject, subjectType: "household_member", householdRole: "viewer" } },
    })));
    render(<RetirementWorkspace />);
    await screen.findByText("$550");
    expect((screen.getByRole("button", { name: "Save Retirement Plan" }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByLabelText("Lifestyle") as HTMLTextAreaElement).disabled).toBe(true);
  });
});
