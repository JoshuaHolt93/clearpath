import type { TransactionReviewView } from "@clearpath/validation";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { TransactionReviewWorkspace, type TransactionQuery } from "./transaction-review-workspace";

const navigation = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => navigation, usePathname: () => "/transactions" }));

const query: TransactionQuery = { q: "", categoryIds: [], categoryNames: "", accountIds: [], minAmount: "", maxAmount: "", month: "", ids: "", sort: "date_desc", page: "1", importMode: false, returnTo: "" };

const groceries = { id: 4, name: "Groceries", kind: "expense", monthlyTarget: 500, isDefault: false, budgetGroupKey: "daily", budgetSortOrder: 2, canManage: true };
const household = { id: 5, name: "Household", kind: "expense", monthlyTarget: 200, isDefault: false, budgetGroupKey: "daily", budgetSortOrder: 3, canManage: true };
const account = { id: 8, name: "Main Checking", accountType: "checking", institution: "Primary Bank", currentBalance: 1800, isManual: false, mask: "1234" };
const transaction = { id: 21, postedDate: "2026-07-18", description: "MARKET 104", displayMerchant: "Local Market", rawDescription: "MARKET 104", amount: -63.45, transactionType: "expense", sourceName: "Main Checking", notes: null, plaidTransactionId: "plaid-21", plaidCategoryLabel: "Food And Drink Groceries", paymentChannelLabel: "In Store", locationSummary: "Raleigh, NC - Store 104", pending: false, category: groceries, account, splits: [] };

function view(overrides: Partial<TransactionReviewView> = {}): TransactionReviewView {
  return {
    session: { ownerUserId: 1, householdName: "Owner Home", selectedPlan: "premium", billingStatus: "active", planDisplayName: "Premier", primaryAccountHolder: true, subject: { id: 1, subjectType: "user", email: "owner@example.com", displayName: "Owner User", firstName: "Owner", avatarInitial: "O", householdRole: null }, featureAccess: [] },
    items: [transaction], total: 1, page: 1, perPage: 20, categories: [groceries, household], accounts: [account],
    duplicateSuggestions: [], budgetActions: { 21: { categoryName: "Groceries", target: 75, targetLabel: "$75", hint: "Start this monthly budget." } }, amortizationActions: {}, recurringTransactionIds: [],
    plaidItems: [{ id: 3, institutionName: "Primary Bank", status: "connected", lastSyncedAt: "2026-07-18T14:00:00Z", errorMessage: null, reconnectRequiredAt: null, accounts: [account] }],
    ...overrides,
  };
}

function jsonResponse(payload: unknown, status = 200) { return new Response(JSON.stringify(payload), { status, headers: { "content-type": "application/json" } }); }

describe("TransactionReviewWorkspace", () => {
  beforeEach(() => { navigation.push.mockReset(); vi.restoreAllMocks(); });

  it("uses an explicit throttled refresh before loading the read-only transaction resource", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => String(input).includes("refresh-stale") ? jsonResponse({ synced: 0, errors: [] }) : jsonResponse(view()));
    render(<TransactionReviewWorkspace query={query} />);
    expect(await screen.findByRole("heading", { name: "Transactions", level: 1 })).toBeDefined();
    expect(await screen.findByText("Local Market")).toBeDefined();
    expect(screen.getByText(/Raleigh, NC - Store 104/)).toBeDefined();
    // Transactions load first; the refresh follows without blocking it.
    expect(fetchMock.mock.calls[0]).toEqual(["/api/transactions", expect.objectContaining({ cache: "no-store" })]);
    await waitFor(() => expect(fetchMock.mock.calls.some((call) => String(call[0]).includes("refresh-stale") && call[1]?.method === "POST")).toBe(true));
  });

  it("keeps filters and sorting in the URL", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => String(input).includes("refresh-stale") ? jsonResponse({ synced: 0, errors: [] }) : jsonResponse(view()));
    render(<TransactionReviewWorkspace query={query} />);
    await screen.findByText("Local Market");
    fireEvent.click(screen.getByRole("button", { name: "Filters" }));
    const form = screen.getByRole("searchbox", { name: "Search" }).closest("form")!;
    fireEvent.change(within(form).getByRole("searchbox", { name: "Search" }), { target: { value: "market" } });
    fireEvent.change(within(form).getByLabelText("Sort"), { target: { value: "amount_desc" } });
    fireEvent.submit(form);
    expect(navigation.push).toHaveBeenCalledWith("/transactions?q=market&sort=amount_desc");
  });

  it("saves a category with apply-to-similar and reloads without another refresh", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      if (String(input).includes("refresh-stale")) return jsonResponse({ synced: 0, errors: [] });
      if (init?.method === "PATCH") return jsonResponse({ transactionId: 21, similarUpdatedCount: 1, ruleCreated: true });
      return jsonResponse(view());
    });
    render(<TransactionReviewWorkspace query={query} />);
    fireEvent.change(await screen.findByLabelText("Category for Local Market"), { target: { value: "5" } });
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(4));
    const mutation = fetchMock.mock.calls.find((call) => call[1]?.method === "PATCH");
    expect(mutation?.[0]).toBe("/api/transactions/21/category");
    expect(JSON.parse(String(mutation?.[1]?.body))).toMatchObject({ categoryId: 5, applyToSimilar: true });
    expect(fetchMock.mock.calls.filter((call) => String(call[0]).includes("refresh-stale"))).toHaveLength(1);
  });

  it("creates a category from the dropdown's + New Category option", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      if (String(input).includes("refresh-stale")) return jsonResponse({ synced: 0, errors: [] });
      if (init?.method === "PATCH") return jsonResponse({ transactionId: 21, transaction: transaction });
      return jsonResponse(view());
    });
    render(<TransactionReviewWorkspace query={query} />);

    const select = await screen.findByLabelText("Category for Local Market");
    // The name field only appears once the sentinel option is chosen.
    expect(screen.queryByLabelText("New category for Local Market")).toBeNull();
    fireEvent.change(select, { target: { value: "__new__" } });

    const nameInput = screen.getByLabelText("New category for Local Market");
    fireEvent.change(nameInput, { target: { value: "Farmers Market" } });
    fireEvent.click(screen.getByRole("button", { name: "Add" }));

    await waitFor(() => {
      const patch = fetchMock.mock.calls.find((call) => call[1]?.method === "PATCH");
      expect(JSON.parse(String(patch?.[1]?.body))).toMatchObject({ newCategoryName: "Farmers Market", categoryId: null });
    });
  });

  it("cancels category creation without saving", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input) =>
      String(input).includes("refresh-stale") ? jsonResponse({ synced: 0, errors: [] }) : jsonResponse(view()));
    render(<TransactionReviewWorkspace query={query} />);

    fireEvent.change(await screen.findByLabelText("Category for Local Market"), { target: { value: "__new__" } });
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(screen.queryByLabelText("New category for Local Market")).toBeNull();
    expect(fetchMock.mock.calls.some((call) => call[1]?.method === "PATCH")).toBe(false);
  });

  it("offers the way back when another workspace sent the user here", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) =>
      String(input).includes("refresh-stale") ? jsonResponse({ synced: 0, errors: [] }) : jsonResponse(view()));
    render(<TransactionReviewWorkspace query={{ ...query, returnTo: "/monthly-plan?section=budgets", categoryNames: "Groceries" }} />);

    const back = await screen.findByRole("link", { name: /Back to Budgets/ });
    expect(back.getAttribute("href")).toBe("/monthly-plan?section=budgets");
    expect(screen.getByText(/Assign transactions to Groceries/)).toBeDefined();
  });

  it("ignores an off-origin return_to", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) =>
      String(input).includes("refresh-stale") ? jsonResponse({ synced: 0, errors: [] }) : jsonResponse(view()));
    // return_to is attacker-controllable, so the strip must not become an
    // open redirect.
    render(<TransactionReviewWorkspace query={{ ...query, returnTo: "https://evil.com/steal" }} />);

    expect(await screen.findByText("Local Market")).toBeDefined();
    expect(screen.queryByRole("link", { name: /Back to/ })).toBeNull();
  });

  it("enforces split totals before sending the exact lines", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      if (String(input).includes("refresh-stale")) return jsonResponse({ synced: 0, errors: [] });
      if (init?.method === "PATCH") return jsonResponse({ transactionId: 21, splitCount: 2 });
      return jsonResponse(view());
    });
    render(<TransactionReviewWorkspace query={query} />);
    // Split now lives in the category cell under Recurring, not behind a
    // row-level "Details" panel (Flask parity).
    fireEvent.click(await screen.findByText("Split Transaction"));
    const save = screen.getByRole("button", { name: "Save Split" });
    expect(save.hasAttribute("disabled")).toBe(true);
    fireEvent.change(screen.getByLabelText("Split 1 amount"), { target: { value: "30" } });
    fireEvent.change(screen.getByLabelText("Split 2 category"), { target: { value: "5" } });
    fireEvent.change(screen.getByLabelText("Split 2 amount"), { target: { value: "33.45" } });
    expect(save.hasAttribute("disabled")).toBe(false);
    fireEvent.click(save);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(4));
    const mutation = fetchMock.mock.calls.find((call) => call[1]?.method === "PATCH");
    expect(JSON.parse(String(mutation?.[1]?.body))).toEqual({ clearSplits: false, splits: [{ categoryId: 4, amount: 30, notes: null }, { categoryId: 5, amount: 33.45, notes: null }] });
  });

  it("renders shared viewer sessions read-only while still loading the full review", async () => {
    const viewer = view({ session: { ...view().session, primaryAccountHolder: false, subject: { ...view().session.subject, subjectType: "household_member", householdRole: "viewer" } } });
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => String(input).includes("refresh-stale") ? jsonResponse({ message: "Editor access required." }, 403) : jsonResponse(viewer));
    render(<TransactionReviewWorkspace query={query} />);
    expect(await screen.findByText("Shared viewer access is read-only.")).toBeDefined();
    expect((screen.getByLabelText("Category for Local Market") as HTMLSelectElement).disabled).toBe(true);
    expect(screen.getByRole("button", { name: "Import & Sync" }).hasAttribute("disabled")).toBe(true);
  });
});
