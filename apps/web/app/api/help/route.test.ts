import { beforeEach, describe, expect, it, vi } from "vitest";

import { GET } from "./route";

const apiGet = vi.hoisted(() => vi.fn());

vi.mock("@clearpath/api-client", () => ({
  createClearPathClient: () => ({ GET: apiGet }),
}));

const me = {
  id: 1,
  email: "owner@example.com",
  display_name: "Owner User",
  household_name: "Owner Home",
  selected_plan: "basic",
  billing_status: "plan_selected",
  is_admin: false,
  session_subject: { id: 1, subject_type: "user", email: "owner@example.com", display_name: "Owner User", first_name: "Owner", avatar_initial: "O", household_role: null },
  primary_account_holder: true,
  plan_display_name: "Plus",
  feature_access: [],
};

describe("Help BFF route", () => {
  beforeEach(() => apiGet.mockReset());

  it("allows income-ready households without a Plaid item, matching Flask ensure_onboarded", async () => {
    apiGet.mockImplementation((path: string) => Promise.resolve({
      data: path === "/v1/me" ? me : { income_ready: true, setup_complete: false },
      error: undefined,
      response: new Response(null, { status: 200 }),
    }));

    const response = await GET(new Request("http://localhost/api/help", { headers: { cookie: "clearpath_session=full" } }));

    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({ session: { ownerUserId: 1 } });
  });

  it("keeps households without an income baseline in onboarding", async () => {
    apiGet.mockImplementation((path: string) => Promise.resolve({
      data: path === "/v1/me" ? me : { income_ready: false, setup_complete: false },
      error: undefined,
      response: new Response(null, { status: 200 }),
    }));

    const response = await GET(new Request("http://localhost/api/help", { headers: { cookie: "clearpath_session=full" } }));

    expect(response.status).toBe(403);
    expect(await response.json()).toEqual({ message: "Finish setup before opening Help." });
  });
});
