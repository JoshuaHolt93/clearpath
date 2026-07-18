import type { PlannerGuidance, PlannerView } from "@clearpath/validation";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PlannerWorkspace } from "./planner-workspace";

const navigation = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => navigation, usePathname: () => "/planner" }));

function guidance(overrides: Partial<PlannerGuidance> = {}): PlannerGuidance {
  return {
    source: "ClearPath rules engine", provider: "openai", model: "gpt-5.5", status: "ready", message: "No saved AI coaching yet.", generatedAt: null,
    items: [{ title: "Cash Flow Review", body: "Review upcoming bills before adding new goals.", level: "warning", type: "cash_flow", disclaimer: "Education only", action: { label: "Review Forecast", target: "monthly_plan_forecast" } }],
    modelOptions: [{ key: "openai", label: "OpenAI", configured: true, models: [{ id: "gpt-5.5", label: "GPT-5.5" }] }, { key: "google", label: "Google", configured: false, models: [{ id: "gemini-2.5-pro", label: "Gemini 2.5 Pro" }] }],
    selectedProvider: "openai", selectedModel: "gpt-5.5", usage: { burstCount: 0, dailyCount: 0, monthlyCount: 0, monthlyCostCents: 0, burstLimit: 8, dailyLimit: 20, monthlyLimit: 300, monthlyCostLimitCents: 250, currentLimitReason: null }, ...overrides,
  };
}

function view(overrides: Partial<PlannerView> = {}): PlannerView {
  return { session: { ownerUserId: 1, householdName: "Owner Home", selectedPlan: "premium", billingStatus: "active", planDisplayName: "Premier", primaryAccountHolder: true, subject: { id: 1, subjectType: "user", email: "owner@example.com", displayName: "Owner", firstName: "Owner", avatarInitial: "O", householdRole: null }, featureAccess: [{ feature: "ai_planner", enabled: true, hidden: false, requiredPlan: "Premier" }, { feature: "ai_coach", enabled: true, hidden: false, requiredPlan: "Premier" }] }, guidance: guidance(), ...overrides };
}

function json(payload: unknown, status = 200) { return new Response(JSON.stringify(payload), { status, headers: { "content-type": "application/json" } }); }

describe("PlannerWorkspace", () => {
  beforeEach(() => { navigation.push.mockReset(); navigation.replace.mockReset(); navigation.refresh.mockReset(); vi.restoreAllMocks(); document.body.style.overflow = ""; });

  it("renders the Flask planner sections and mapped action", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(json(view()));
    render(<PlannerWorkspace />);
    expect(await screen.findByRole("heading", { name: "AI Model Preference" })).toBeDefined();
    expect(screen.getByRole("heading", { name: "Investment-Option Awareness" })).toBeDefined();
    expect(screen.getByRole("heading", { name: "Financial Coaching" })).toBeDefined();
    expect(screen.getByText("Guardrail Boundary")).toBeDefined();
    expect(screen.getByRole("link", { name: "Review Forecast" }).getAttribute("href")).toBe("/monthly-plan?section=forecast");
  });

  it("filters models by provider and saves the explicit preference", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(json(view())).mockResolvedValueOnce(json(guidance({ selectedProvider: "google", selectedModel: "gemini-2.5-pro" })));
    render(<PlannerWorkspace />);
    fireEvent.change(await screen.findByLabelText("AI Provider"), { target: { value: "google" } });
    expect((screen.getByLabelText("Model") as HTMLSelectElement).value).toBe("gemini-2.5-pro");
    fireEvent.submit(screen.getByRole("button", { name: "Save Preference" }).closest("form")!);
    await screen.findByText("AI model preference saved.");
    expect(fetchMock.mock.calls[1]?.[0]).toBe("/api/planner/preferences");
    expect(JSON.parse(String((fetchMock.mock.calls[1]?.[1] as RequestInit).body))).toEqual({ provider: "google", model: "gemini-2.5-pro" });
  });

  it("generates guidance only from the explicit command", async () => {
    const updated = guidance({ status: "ai", message: "Updated", generatedAt: "2026-07-18T12:00:00Z", items: [{ title: "Updated Review", body: "Review the new forecast.", level: "good", type: "forecast", disclaimer: null, action: null }] });
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(json(view())).mockResolvedValueOnce(json(updated));
    render(<PlannerWorkspace />);
    fireEvent.click(await screen.findByRole("button", { name: "Generate AI Guidance" }));
    expect(await screen.findByText("Updated Review")).toBeDefined();
    expect(fetchMock).toHaveBeenNthCalledWith(2, "/api/planner/guidance", { method: "POST" });
  });

  it("keeps page coaching available to a shared viewer", async () => {
    const viewer = view({ session: { ...view().session, primaryAccountHolder: false, subject: { ...view().session.subject, subjectType: "household_member", householdRole: "viewer" } } });
    const coachResponse = { source: "ClearPath AI", provider: "openai", model: "gpt-5.5", status: "ai", message: "Reviewed", items: [{ title: "Page Review", body: "The forecast deserves attention.", level: "info", type: "page_context", disclaimer: null, action: null }] };
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(json(viewer)).mockResolvedValueOnce(json(coachResponse));
    render(<PlannerWorkspace />);
    expect((await screen.findByRole("button", { name: "Generate AI Guidance" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Ask AI Coach" }));
    const dialog = screen.getByRole("dialog", { name: "Ask AI Coach" });
    fireEvent.change(within(dialog).getByLabelText("Ask a question about this page"), { target: { value: "What stands out?" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Send to AI Coach" }));
    expect(await within(dialog).findByText("Page Review")).toBeDefined();
    expect(fetchMock.mock.calls[1]?.[0]).toBe("/api/planner/page-context");
  });

  it("redirects a feature-locked session to plan selection", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(json({ message: "AI Planner requires ClearPath Premier." }, 403));
    render(<PlannerWorkspace />);
    await waitFor(() => expect(navigation.replace).toHaveBeenCalledWith("/select-plan"));
  });
});
