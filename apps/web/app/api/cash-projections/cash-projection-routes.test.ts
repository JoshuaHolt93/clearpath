import { beforeEach, describe, expect, it, vi } from "vitest";

import { POST as autoRecurring } from "./auto-recurring/[detectionKey]/route";
import { PATCH as calendarFeed } from "./calendar-feed/route";
import { PATCH as preferences } from "./preferences/route";
import { POST as refresh } from "./refresh/route";
import { GET } from "./route";

const apiGet = vi.hoisted(() => vi.fn());
const apiPost = vi.hoisted(() => vi.fn());
const apiPatch = vi.hoisted(() => vi.fn());

vi.mock("@clearpath/api-client", () => ({
  createClearPathClient: () => ({ GET: apiGet, POST: apiPost, PATCH: apiPatch }),
}));

function ok(data: unknown) {
  return { data, error: undefined, response: new Response(null, { status: 200 }) };
}

function graph() {
  return {
    points: "0,50 100,20",
    zero_axis_pct: 90,
    show_zero_line: true,
    min_value: -100,
    max_value: 2500,
    month_markers: [{ label: "August", axis_label: "Aug", x_pct: 50 }],
    point_rows: [{ x_pct: 0, y_pct: 50, date_label: "Jul 18", balance: 1800, balance_basis: "Actual" }],
  };
}

function event() {
  return {
    date: "2026-07-18",
    description: "Paycheck",
    amount: 2000,
    item_type: "income",
    source: "paycheck",
    category_label: "Income",
    notes: null,
    source_id: null,
    signed_amount: 2000,
    account_name: null,
    pending: false,
  };
}

function day() {
  return {
    date: "2026-07-18",
    day: 18,
    weekday: "Saturday",
    is_today: true,
    is_past: false,
    events: [event()],
    actual_events: [],
    scheduled_events: [event()],
    actual_balance: 1800,
    balance_basis: "Projected",
    net_change: 2000,
    actual_change: 0,
    scheduled_change: 2000,
    ending_balance: 3800,
  };
}

function anchor() {
  return {
    date: "2026-07-18",
    balance: 1800,
    checking_balance: 1800,
    account_count: 1,
    checking_account_count: 1,
    included_accounts: [{
      id: 9,
      name: "Main Checking",
      institution: "Primary Bank",
      account_type: "checking",
      balance: 1800,
      mask: "1234",
      cash_projection_role: "auto",
    }],
    uses_cash_accounts: true,
  };
}

function period() {
  return {
    month: "2026-07-01",
    month_label: "July 2026",
    start_date: "2026-07-18",
    end_date: "2026-07-24",
    start_balance: 1800,
    end_balance: 3800,
    balance_anchor: anchor(),
    lowest_balance: { date: "2026-07-18", balance: 1800 },
    highest_balance: { date: "2026-07-24", balance: 3800 },
    days: [day()],
    weeks: [{ week_start: "2026-07-18", week_end: "2026-07-24", days: [day()], income: 2000, expenses: 0, ending_balance: 3800, net_change: 2000 }],
    calendar_cells: [null, day()],
    events: [event()],
    trend: {
      current_variable_spend: 325,
      planned_variable_spend: 800,
      average_first_half_share: 0.48,
      affects_projection: false,
      message: "Variable spending is running near plan.",
    },
    graph: graph(),
  };
}

function projectionResponse() {
  return {
    horizon: "week",
    view: "calendar",
    projection: period(),
    projection_range: {
      start_month: "2026-07-01",
      start_date: "2026-07-18",
      end_date: "2026-07-24",
      months: 0,
      projections: [period()],
      days: [day()],
      events: [event()],
      start_balance: 1800,
      end_balance: 3800,
      balance_anchor: anchor(),
      lowest_balance: { date: "2026-07-18", balance: 1800 },
      highest_balance: { date: "2026-07-24", balance: 3800 },
      graph: graph(),
    },
    previous_month: "2026-06-01",
    next_month: "2026-08-01",
    custom_start: "2026-07-18",
    custom_end: "2026-08-17",
    custom_min_date: "2026-01-18",
    custom_max_date: "2027-01-18",
    projection_min_month: "2026-01",
    projection_max_month: "2027-01",
    account_rows: [{
      account_id: 9,
      name: "Main Checking",
      institution: "Primary Bank",
      account_type: "checking",
      balance: 1800,
      mask: "1234",
      role: "auto",
      included: true,
      status_label: "Included",
      status_class: "badge-green",
      status_detail: "Primary operating cash account",
    }],
    detected_recurring: [{
      detection_key: "merchant:fitness",
      name: "Local Fitness",
      amount: 45,
      frequency: "monthly",
      start_date: "2026-08-01",
      second_day_of_month: null,
      category_label: "Fitness",
      notes: null,
      last_seen: "2026-07-01",
    }],
    ignored_recurring: [],
    calendar_feed: { enabled: false, feed_url: null, webcal_url: null, google_url: null, generated_at: null, history_months: 3 },
    refresh: null,
  };
}

describe("Cash Balance Projections BFF", () => {
  beforeEach(() => {
    apiGet.mockReset();
    apiPost.mockReset();
    apiPatch.mockReset();
  });

  it("maps the typed projection and keeps GET free of refresh side effects", async () => {
    apiGet.mockResolvedValue(ok(projectionResponse()));

    const response = await GET(new Request("http://localhost/api/cash-projections?month=2026-07&horizon=week&view=list", { headers: { cookie: "clearpath_session=full" } }));

    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({
      horizon: "week",
      projectionRange: { startBalance: 1800, endBalance: 3800 },
      accountRows: [{ accountId: 9, name: "Main Checking", role: "auto" }],
      detectedRecurring: [{ detectionKey: "merchant:fitness", amount: 45 }],
      calendarFeed: { enabled: false, historyMonths: 3 },
    });
    expect(apiGet).toHaveBeenCalledWith("/v1/cash-projections", expect.objectContaining({
      params: { query: { month: "2026-07", horizon: "week", view: "list", start_date: undefined, end_date: undefined } },
    }));
    expect(apiPost).not.toHaveBeenCalled();
    expect(apiPatch).not.toHaveBeenCalled();
  });

  it("forwards explicit refresh and returns the refreshed projection", async () => {
    const refreshed = { ...projectionResponse(), refresh: { synced: 1, errors: [] } };
    apiPost.mockResolvedValue(ok(refreshed));

    const response = await refresh(new Request("http://localhost/api/cash-projections/refresh", {
      method: "POST",
      headers: { "content-type": "application/json", cookie: "clearpath_session=full" },
      body: JSON.stringify({ month: "2026-07", horizon: "week", view: "calendar" }),
    }));

    expect(response.status).toBe(200);
    expect((await response.json()).refresh).toEqual({ synced: 1, errors: [] });
    expect(apiPost).toHaveBeenCalledWith("/v1/cash-projections/refresh", expect.objectContaining({
      body: expect.objectContaining({ month: "2026-07", horizon: "week", view: "calendar" }),
    }));
  });

  it("persists only non-custom horizons through the explicit preference endpoint", async () => {
    apiPatch.mockResolvedValue(ok({ default_horizon: "3m" }));

    const response = await preferences(new Request("http://localhost/api/cash-projections/preferences", {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ defaultHorizon: "3m" }),
    }));

    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ defaultHorizon: "3m" });
    expect(apiPatch).toHaveBeenCalledWith("/v1/cash-projections/preferences", expect.objectContaining({ body: { default_horizon: "3m" } }));
  });

  it("forwards detected-recurring conversion fields and maps the updated page", async () => {
    apiPost.mockResolvedValue(ok(projectionResponse()));
    const response = await autoRecurring(new Request("http://localhost/api/cash-projections/auto-recurring/merchant%3Afitness", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        action: "save",
        horizon: "3m",
        view: "list",
        name: "Local Fitness Adjusted",
        amount: 50,
        frequency: "semimonthly",
        scheduleStartDate: "2026-08-01",
        secondDate: "2026-08-15",
        categoryLabel: "Fitness",
      }),
    }), { params: Promise.resolve({ detectionKey: "merchant:fitness" }) });

    expect(response.status).toBe(200);
    expect(apiPost).toHaveBeenCalledWith("/v1/cash-projections/auto-recurring/{detection_key}", expect.objectContaining({
      params: { path: { detection_key: "merchant:fitness" } },
      body: expect.objectContaining({ action: "save", schedule_start_date: "2026-08-01", second_date: "2026-08-15" }),
    }));
  });

  it("maps calendar-feed token lifecycle responses", async () => {
    apiPatch.mockResolvedValue(ok({
      enabled: true,
      feed_url: "https://api.example/v1/cash-projections/calendar/private.ics",
      webcal_url: "webcal://api.example/v1/cash-projections/calendar/private.ics",
      google_url: "https://calendar.google.com/calendar/render?cid=private",
      generated_at: "2026-07-18T12:00:00Z",
      history_months: 3,
    }));

    const response = await calendarFeed(new Request("http://localhost/api/cash-projections/calendar-feed", {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ action: "enable" }),
    }));

    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({ enabled: true, feedUrl: expect.stringContaining("private.ics"), historyMonths: 3 });
    expect(apiPatch).toHaveBeenCalledWith("/v1/cash-projections/calendar-feed", expect.objectContaining({ body: { action: "enable" } }));
  });
});
