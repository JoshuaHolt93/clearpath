import { beforeEach, describe, expect, it, vi } from "vitest";

import { POST as coach } from "./page-context/route";
import { PATCH as preference } from "./preferences/route";
import { POST as generate } from "./guidance/route";
import { GET } from "./route";

const apiGet = vi.hoisted(() => vi.fn());
const apiPost = vi.hoisted(() => vi.fn());
const apiPatch = vi.hoisted(() => vi.fn());
vi.mock("@clearpath/api-client", () => ({ createClearPathClient: () => ({ GET: apiGet, POST: apiPost, PATCH: apiPatch }) }));

function guidance() {
  return {
    source: "ClearPath rules engine", provider: "openai", model: "gpt-5.5", status: "ready", message: "Ready", generated_at: null,
    items: [{ title: "Cash Flow Review", body: "Review upcoming bills.", level: "warning", type: "cash_flow", disclaimer: "Education only", action: { label: "Review Forecast", target: "monthly_plan_forecast" } }],
    model_options: [{ key: "openai", label: "OpenAI", configured: true, models: [{ id: "gpt-5.5", label: "GPT-5.5" }] }], selected_provider: "openai", selected_model: "gpt-5.5",
    usage: { burst_count: 1, daily_count: 2, monthly_count: 3, monthly_cost_cents: .4, burst_limit: 8, daily_limit: 20, monthly_limit: 300, monthly_cost_limit_cents: 250, current_limit_reason: null },
  };
}

function me() {
  return { id: 1, email: "owner@example.com", display_name: "Owner", household_name: "Owner Home", selected_plan: "premium", billing_status: "active", is_admin: false, session_subject: { id: 1, subject_type: "user", email: "owner@example.com", display_name: "Owner", first_name: "Owner", avatar_initial: "O", household_role: null }, primary_account_holder: true, plan_display_name: "Premier", feature_access: [{ feature: "ai_coach", enabled: true, hidden: false, required_plan: "Premier" }] };
}

function ok(data: unknown) { return { data, error: undefined, response: new Response(null, { status: 200 }) }; }

describe("planner BFF routes", () => {
  beforeEach(() => { apiGet.mockReset(); apiPost.mockReset(); apiPatch.mockReset(); });

  it("combines guidance with the signed-in session", async () => {
    apiGet.mockImplementation((path: string) => Promise.resolve(ok(path === "/v1/planner/guidance" ? guidance() : me())));
    const response = await GET(new Request("http://localhost/api/planner", { headers: { cookie: "clearpath_session=full" } }));
    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({ session: { primaryAccountHolder: true }, guidance: { selectedModel: "gpt-5.5", items: [{ action: { target: "monthly_plan_forecast" } }], usage: { dailyCount: 2 } } });
    expect(apiGet).toHaveBeenCalledWith("/v1/planner/guidance", { headers: { cookie: "clearpath_session=full" } });
    expect(response.headers.get("cache-control")).toBe("no-store");
  });

  it("keeps guidance generation an explicit empty-body mutation", async () => {
    apiPost.mockResolvedValue(ok({ ...guidance(), status: "ai", generated_at: "2026-07-18T12:00:00Z" }));
    const response = await generate(new Request("http://localhost/api/planner/guidance", { method: "POST", headers: { cookie: "clearpath_session=full" } }));
    expect(response.status).toBe(200);
    expect((await response.json()).status).toBe("ai");
    expect(apiPost).toHaveBeenCalledWith("/v1/planner/guidance/generate", { body: {}, headers: { cookie: "clearpath_session=full" } });
  });

  it("validates and forwards model preferences", async () => {
    apiPatch.mockResolvedValue(ok(guidance()));
    const response = await preference(new Request("http://localhost/api/planner/preferences", { method: "PATCH", headers: { "content-type": "application/json", cookie: "clearpath_session=full" }, body: JSON.stringify({ provider: "openai", model: "gpt-5.5" }) }));
    expect(response.status).toBe(200);
    expect(apiPatch).toHaveBeenCalledWith("/v1/planner/preferences", { body: { provider: "openai", model: "gpt-5.5" }, headers: { cookie: "clearpath_session=full" } });
    const invalid = await preference(new Request("http://localhost/api/planner/preferences", { method: "PATCH", headers: { "content-type": "application/json" }, body: "{}" }));
    expect(invalid.status).toBe(422);
  });

  it("maps browser page context into the FastAPI request", async () => {
    apiPost.mockResolvedValue(ok({ source: "ClearPath AI", provider: "openai", model: "gpt-5.5", status: "ai", message: "Reviewed", items: [{ title: "Budget Review", body: "Review the flexible category.", level: "info", type: "page_context", disclaimer: null, action: null }] }));
    const response = await coach(new Request("http://localhost/api/planner/page-context", { method: "POST", headers: { "content-type": "application/json", cookie: "clearpath_session=full" }, body: JSON.stringify({ path: "/analytics", title: "Analytics", section: "", visibleText: "Cash flow", question: "What stands out?" }) }));
    expect(response.status).toBe(200);
    expect((await response.json()).items[0].title).toBe("Budget Review");
    expect(apiPost).toHaveBeenCalledWith("/v1/planner/page-context", { body: { path: "/analytics", title: "Analytics", section: "", visible_text: "Cash flow", question: "What stands out?" }, headers: { cookie: "clearpath_session=full" } });
  });
});
