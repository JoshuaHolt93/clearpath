import type { CategoryRulesView } from "@clearpath/validation";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CategoryRulesWorkspace } from "./category-rules-workspace";

const navigation = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => navigation, usePathname: () => "/category-rules" }));

const groceries = { id: 4, name: "Groceries", kind: "expense", monthlyTarget: 600, isDefault: false, canManage: true };
function view(overrides: Partial<CategoryRulesView> = {}): CategoryRulesView {
  return {
    session: { ownerUserId: 1, householdName: "Owner Home", selectedPlan: "basic", billingStatus: "active", planDisplayName: "Plus", primaryAccountHolder: true, subject: { id: 1, subjectType: "user", email: "owner@example.com", displayName: "Owner User", firstName: "Owner", avatarInitial: "O", householdRole: null }, featureAccess: [] },
    categories: [groceries, { id: 5, name: "Dining/Eating Out", kind: "expense", monthlyTarget: 250, isDefault: false, canManage: true }],
    rules: [{ id: 9, category: groceries, matchText: "kroger", matchType: "contains", ruleLogic: "custom", conditions: [{ field: "description", operator: "contains", value: "kroger", valueSecondary: "", group: "primary", join: "and" }, { field: "amount", operator: "between", value: "25", valueSecondary: "75", group: "primary", join: "or" }], summary: "Description Contains kroger OR Amount Between 25 And 75", createdAt: "2026-07-18T12:00:00", updatedAt: "2026-07-18T12:00:00", appliedCount: null }],
    ...overrides,
  };
}
function json(payload: unknown, status = 200) { return new Response(JSON.stringify(payload), { status, headers: { "content-type": "application/json" } }); }

describe("CategoryRulesWorkspace", () => {
  beforeEach(() => { navigation.push.mockReset(); navigation.replace.mockReset(); navigation.refresh.mockReset(); vi.restoreAllMocks(); });

  it("loads the editor and honors canonical transaction prefill", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(json(view()));
    render(<CategoryRulesWorkspace prefill={{ field: "description", operator: "contains", value: "Local Market", categoryId: 4 }} />);
    const create = await screen.findByRole("region", { name: "Create A Rule" });
    expect((within(create).getByLabelText("Condition 1 value") as HTMLInputElement).value).toBe("Local Market");
    expect((within(create).getByLabelText("Apply Category") as HTMLSelectElement).value).toBe("4");
    expect(screen.getByText("Description Contains \"kroger\"")).toBeDefined();
    expect(screen.getByText("+ 1 More")).toBeDefined();
  });

  it("creates a mixed rule and surfaces the applied transaction count", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (_input, init) => init?.method === "POST" ? json({ ruleId: 10, appliedCount: 2 }, 201) : json(view()));
    render(<CategoryRulesWorkspace prefill={{ field: "description", operator: "contains", value: "", categoryId: null }} />);
    const create = await screen.findByRole("region", { name: "Create A Rule" });
    fireEvent.change(within(create).getByLabelText("Condition 1 value"), { target: { value: "Kroger" } });
    fireEvent.click(within(create).getByRole("button", { name: "Add Condition" }));
    fireEvent.change(within(create).getByLabelText("Condition 2 join"), { target: { value: "or" } });
    fireEvent.change(within(create).getByLabelText("Condition 2 field"), { target: { value: "amount" } });
    fireEvent.change(within(create).getByLabelText("Condition 2 operator"), { target: { value: "between" } });
    fireEvent.change(within(create).getByLabelText("Condition 2 value"), { target: { value: "25" } });
    fireEvent.change(within(create).getByLabelText("Condition 2 upper limit"), { target: { value: "75" } });
    fireEvent.change(within(create).getByLabelText("Apply Category"), { target: { value: "4" } });
    fireEvent.click(within(create).getByRole("button", { name: "Save Rule" }));
    expect(await screen.findByText("Rule created and applied to 2 existing transactions.")).toBeDefined();
    const sent = JSON.parse(String(fetchMock.mock.calls.find(([, init]) => init?.method === "POST")?.[1]?.body));
    expect(sent).toMatchObject({ categoryId: 4, conditions: [{ value: "Kroger" }, { field: "amount", operator: "between", valueSecondary: "75", join: "or" }] });
  });

  it("keeps shared viewers read-only while preserving saved-rule detail", async () => {
    const viewer = view({ session: { ...view().session, primaryAccountHolder: false, subject: { ...view().session.subject, subjectType: "household_member", householdRole: "viewer" } } });
    vi.spyOn(globalThis, "fetch").mockResolvedValue(json(viewer));
    render(<CategoryRulesWorkspace prefill={{ field: "description", operator: "contains", value: "", categoryId: null }} />);
    expect(await screen.findByText("Shared viewer access is read-only.")).toBeDefined();
    expect(screen.getAllByRole("button", { name: "Manage Categories" }).every((button) => button.hasAttribute("disabled"))).toBe(true);
    fireEvent.click(screen.getByText("Description Contains \"kroger\""));
    expect(await screen.findByRole("button", { name: "Save Changes" })).toHaveProperty("disabled", true);
    expect(screen.getByRole("button", { name: "Delete Rule" })).toHaveProperty("disabled", true);
  });

  it("manages categories without activating a budget from the rule page", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (_input, init) => init?.method === "POST" ? json({ categoryId: 6, name: "Pharmacy" }, 201) : json(view()));
    render(<CategoryRulesWorkspace prefill={{ field: "description", operator: "contains", value: "", categoryId: null }} />);
    await screen.findByText("Description Contains \"kroger\"");
    fireEvent.click(screen.getAllByRole("button", { name: "Manage Categories" })[0]);
    const dialog = await screen.findByRole("dialog", { name: "Manage Categories" });
    expect(document.body.style.overflow).toBe("hidden");
    fireEvent.change(within(dialog).getByRole("textbox", { name: "Name" }), { target: { value: "Pharmacy" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Add Category" }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(true));
    const sent = JSON.parse(String(fetchMock.mock.calls.find(([, init]) => init?.method === "POST")?.[1]?.body));
    expect(sent).toEqual({ name: "Pharmacy", kind: "expense", activateBudget: false });
  });
});
