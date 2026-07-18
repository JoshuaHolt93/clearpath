import { beforeEach, describe, expect, it, vi } from "vitest";

import { PATCH, DELETE } from "./[ruleId]/route";
import { GET, POST } from "./route";

const apiGet = vi.hoisted(() => vi.fn());
const apiPost = vi.hoisted(() => vi.fn());
const apiPatch = vi.hoisted(() => vi.fn());
const apiDelete = vi.hoisted(() => vi.fn());

vi.mock("@clearpath/api-client", () => ({ createClearPathClient: () => ({ GET: apiGet, POST: apiPost, PATCH: apiPatch, DELETE: apiDelete }) }));

function ok(data: unknown, status = 200) { return { data, error: undefined, response: new Response(null, { status }) }; }
function me() { return { id: 1, email: "owner@example.com", display_name: "Owner User", household_name: "Owner Home", selected_plan: "basic", billing_status: "active", is_admin: false, session_subject: { id: 1, subject_type: "user", email: "owner@example.com", display_name: "Owner User", first_name: "Owner", avatar_initial: "O", household_role: null }, primary_account_holder: true, plan_display_name: "Plus", feature_access: [] }; }
function category() { return { id: 4, user_id: 1, name: "Groceries", kind: "expense", monthly_target: 600, is_default: false, budget_group_key: "flexible", budget_sort_order: 1, can_manage: true }; }
function rule() { return { id: 9, category: category(), match_text: "kroger", match_type: "contains", rule_logic: "custom", conditions: [{ field: "description", operator: "contains", value: "kroger", value_secondary: "", group: "primary", join: "and" }, { field: "amount", operator: "between", value: "25", value_secondary: "75", group: "primary", join: "or" }], summary: "Description Contains kroger OR Amount Between 25 And 75", created_at: "2026-07-18T12:00:00", updated_at: "2026-07-18T12:00:00", applied_count: null }; }

describe("Category rules BFF", () => {
  beforeEach(() => { apiGet.mockReset(); apiPost.mockReset(); apiPatch.mockReset(); apiDelete.mockReset(); });

  it("combines rule editor data and session without a mutation on GET", async () => {
    apiGet.mockImplementation((path: string) => Promise.resolve(ok(path === "/v1/category-rules" ? { rules: [rule()], categories: [category()] } : me())));
    const response = await GET(new Request("http://localhost/api/category-rules", { headers: { cookie: "clearpath_session=full" } }));
    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({ rules: [{ id: 9, category: { name: "Groceries", canManage: true }, conditions: [{ value: "kroger" }, { valueSecondary: "75", join: "or" }] }], session: { primaryAccountHolder: true } });
    expect(apiPost).not.toHaveBeenCalled();
  });

  it("forwards the four-condition editor contract and applied count", async () => {
    apiPost.mockResolvedValue(ok({ ...rule(), applied_count: 3 }, 201));
    const body = { categoryId: 4, conditions: [{ field: "description", operator: "contains", value: "Kroger", valueSecondary: "", group: "primary", join: "and" }, { field: "amount", operator: "between", value: "25", valueSecondary: "75", group: "primary", join: "or" }] };
    const response = await POST(new Request("http://localhost/api/category-rules", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) }));
    expect(response.status).toBe(201);
    expect(await response.json()).toEqual({ ruleId: 9, appliedCount: 3 });
    expect(apiPost).toHaveBeenCalledWith("/v1/category-rules", expect.objectContaining({ body: { category_id: 4, match_text: null, conditions: [expect.objectContaining({ value: "Kroger", value_secondary: "" }), expect.objectContaining({ operator: "between", value_secondary: "75", join: "or" })] } }));

    const invalid = await POST(new Request("http://localhost/api/category-rules", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ categoryId: 4, conditions: Array.from({ length: 5 }, (_, index) => ({ ...body.conditions[0], value: String(index) })) }) }));
    expect(invalid.status).toBe(422);
    expect(apiPost).toHaveBeenCalledTimes(1);
  });

  it("forwards update and confirmed deletion as distinct resource mutations", async () => {
    apiPatch.mockResolvedValue(ok({ ...rule(), applied_count: 1 }));
    apiDelete.mockResolvedValue(ok(rule()));
    const body = { categoryId: 4, conditions: [{ field: "description", operator: "equals", value: "Kroger", valueSecondary: "", group: "primary", join: "and" }] };
    const updated = await PATCH(new Request("http://localhost/api/category-rules/9", { method: "PATCH", headers: { "content-type": "application/json" }, body: JSON.stringify(body) }), { params: Promise.resolve({ ruleId: "9" }) });
    expect(await updated.json()).toEqual({ ruleId: 9, appliedCount: 1 });
    expect(apiPatch).toHaveBeenCalledWith("/v1/category-rules/{rule_id}", expect.objectContaining({ params: { path: { rule_id: 9 } }, body: expect.objectContaining({ category_id: 4 }) }));
    const deleted = await DELETE(new Request("http://localhost/api/category-rules/9", { method: "DELETE", headers: { "content-type": "application/json" }, body: JSON.stringify({ confirm: true }) }), { params: Promise.resolve({ ruleId: "9" }) });
    expect(await deleted.json()).toEqual({ deletedRuleId: 9 });
    expect(apiDelete).toHaveBeenCalledWith("/v1/category-rules/{rule_id}", expect.objectContaining({ body: { confirm: true } }));
  });
});
