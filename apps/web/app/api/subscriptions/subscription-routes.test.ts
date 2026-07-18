import { beforeEach, describe, expect, it, vi } from "vitest";

import { POST as importCsv } from "../subscription-imports/route";
import { PATCH } from "./[subscriptionId]/route";
import { POST as ignoreEvidence } from "./[subscriptionId]/evidence/[transactionId]/ignore/route";
import { GET, POST } from "./route";
import { POST as scan } from "./scan/route";

const apiGet = vi.hoisted(() => vi.fn());
const apiPost = vi.hoisted(() => vi.fn());
const apiPatch = vi.hoisted(() => vi.fn());

vi.mock("@clearpath/api-client", () => ({ createClearPathClient: () => ({ GET: apiGet, POST: apiPost, PATCH: apiPatch }) }));

function ok(data: unknown, status = 200) { return { data, error: undefined, response: new Response(null, { status }) }; }
function me() { return { id: 1, email: "owner@example.com", display_name: "Owner User", household_name: "Owner Home", selected_plan: "premium", billing_status: "active", is_admin: false, session_subject: { id: 1, subject_type: "user", email: "owner@example.com", display_name: "Owner User", first_name: "Owner", avatar_initial: "O", household_role: null }, primary_account_holder: true, plan_display_name: "Premier", feature_access: [{ feature: "subscriptions", enabled: true, hidden: false, required_plan: "Plus" }] }; }
function subscription() { return { id: 7, merchant_key: "netflix", name: "Netflix", category: "Consumer Subscriptions", service_category: "Streaming", amount: 18.99, monthly_amount: 18.99, annual_amount: 227.88, cycle: "Monthly", cycle_days: 30, confidence: .95, status: "active", cancel_url: "https://netflix.com/cancel", replaceable: true, first_seen: "2026-05-01", last_seen: "2026-06-30", next_charge_date: "2026-07-30", notes: null, is_manual: false, cycle_is_manual: false, evidence: [{ id: 41, date: "2026-06-30", description: "NETFLIX.COM", amount: 18.99 }] }; }
function listing() { return { subscriptions: [subscription()], summary: { active_count: 1, review_count: 0, action_count: 1, manage_link_count: 1, monthly_total: 18.99, annual_total: 227.88, potential_savings: 18.99, average_confidence: 95, transaction_count: 3 }, category_breakdown: [{ category: "Streaming", amount: 18.99, percent: 100 }], opportunities: [{ subscription_id: 7, reason: "Replaceable service" }], upcoming_subscription_ids: [7], statuses: { active: "Active", review: "Review", canceling: "Canceling", canceled: "Canceled", ignored: "Ignored" }, cycles: ["Weekly", "Biweekly", "Monthly", "Quarterly", "Annual"] }; }

describe("Subscriptions BFF", () => {
  beforeEach(() => { apiGet.mockReset(); apiPost.mockReset(); apiPatch.mockReset(); });

  it("combines the subscription resource and session without scanning on GET", async () => {
    apiGet.mockImplementation((path: string) => Promise.resolve(ok(path === "/v1/subscriptions" ? listing() : me())));
    const response = await GET(new Request("http://localhost/api/subscriptions", { headers: { cookie: "clearpath_session=full" } }));
    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({ subscriptions: [{ name: "Netflix", monthlyAmount: 18.99, evidence: [{ id: 41 }] }], summary: { averageConfidence: 95 }, upcomingSubscriptionIds: [7] });
    expect(apiPost).not.toHaveBeenCalled();
  });

  it("forwards manual creation and exact scan semantics", async () => {
    apiPost.mockResolvedValueOnce(ok(subscription(), 201)).mockResolvedValueOnce(ok({ synced_count: 1, subscriptions: [subscription()] }));
    const created = await POST(new Request("http://localhost/api/subscriptions", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ name: "Netflix", amount: 18.99, cycle: "Monthly", nextChargeDate: "2026-07-30", notes: null }) }));
    expect(created.status).toBe(201);
    expect(apiPost).toHaveBeenNthCalledWith(1, "/v1/subscriptions", expect.objectContaining({ body: { name: "Netflix", amount: 18.99, cycle: "Monthly", next_charge_date: "2026-07-30", notes: null } }));
    const scanned = await scan(new Request("http://localhost/api/subscriptions/scan", { method: "POST" }));
    expect(await scanned.json()).toEqual({ syncedCount: 1 });
  });

  it("forwards unified status, cycle, notes, and website changes", async () => {
    apiPatch.mockResolvedValue(ok({ ...subscription(), status: "ignored", notes: "Duplicate", cycle: "Annual", cancel_url: null }));
    const response = await PATCH(new Request("http://localhost/api/subscriptions/7", { method: "PATCH", headers: { "content-type": "application/json" }, body: JSON.stringify({ status: "ignored", notes: "Duplicate", cycle: "Annual", cancelUrl: null }) }), { params: Promise.resolve({ subscriptionId: "7" }) });
    expect(response.status).toBe(200);
    expect(apiPatch).toHaveBeenCalledWith("/v1/subscriptions/{subscription_id}", expect.objectContaining({ params: { path: { subscription_id: 7 } }, body: { status: "ignored", notes: "Duplicate", cycle: "Annual", cancel_url: null } }));
  });

  it("preserves evidence-ignore and CSV import operations", async () => {
    apiPost.mockResolvedValueOnce(ok({ ...subscription(), evidence: [] })).mockResolvedValueOnce(ok({ imported: 3, synced_count: 1 }));
    const ignored = await ignoreEvidence(new Request("http://localhost/api/subscriptions/7/evidence/41/ignore", { method: "POST" }), { params: Promise.resolve({ subscriptionId: "7", transactionId: "41" }) });
    expect(await ignored.json()).toEqual({ subscriptionId: 7, evidenceCount: 0 });
    const imported = await importCsv(new Request("http://localhost/api/subscription-imports", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ csvText: "Date,Description,Amount\n07/01/2026,Netflix,-18.99" }) }));
    expect(await imported.json()).toEqual({ imported: 3, syncedCount: 1 });
    expect(apiPost).toHaveBeenNthCalledWith(2, "/v1/subscription-imports", expect.objectContaining({ body: { csv_text: expect.stringContaining("Netflix"), csv_base64: null } }));
  });
});
