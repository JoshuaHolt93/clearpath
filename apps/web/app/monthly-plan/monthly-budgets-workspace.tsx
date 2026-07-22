"use client";

import { monthlyBudgetsViewSchema, type MonthlyBudgetsView } from "@clearpath/validation";
import {
  ArrowDown,
  ArrowUp,
  CalendarDays,
  ChevronRight,
  GripVertical,
  LayoutList,
  Layers3,
  Plus,
  Save,
  Trash2,
  TriangleAlert,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { type DragEvent, type FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import { AuthenticatedPageFrame } from "../authenticated-shell";
import { refreshLiveBankData } from "@/lib/live-bank-refresh";

import { SavingIndicator } from "../saving-indicator";
import styles from "./monthly-budgets.module.css";

export type MonthlyBudgetQuery = {
  budgetView: "list" | "grouped";
  budgetSort: string;
  budgetMonth: string;
  onboardingComplete: boolean;
};

type BudgetRow = MonthlyBudgetsView["budgetSections"][number]["rows"][number];

function currency(value: number, decimals = 0): string {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: decimals, maximumFractionDigits: decimals }).format(Math.abs(value));
}

function signedCurrency(value: number): string {
  return `${value < 0 ? "-" : ""}${currency(value)}`;
}

function routeForQuery(query: MonthlyBudgetQuery): string {
  const params = new URLSearchParams({ section: "budgets" });
  if (query.budgetView === "grouped") params.set("budget_view", "grouped");
  if (query.budgetSort !== "custom") params.set("budget_sort", query.budgetSort);
  if (query.budgetMonth) params.set("budget_month", query.budgetMonth);
  if (query.onboardingComplete) params.set("onboarding", "complete");
  return `/monthly-plan?${params.toString()}`;
}

function apiRouteForQuery(query: MonthlyBudgetQuery): string {
  return `/api${routeForQuery(query)}`;
}

function transactionHref(row: BudgetRow): string {
  const params = new URLSearchParams();
  if (row.transactionIds.length) params.set("ids", row.transactionIds.join(","));
  else if (row.categoryId) params.set("category_id", String(row.categoryId));
  return `/transactions${params.size ? `?${params.toString()}` : ""}`;
}

async function responseMessage(response: Response, fallback: string): Promise<string> {
  const payload = await response.json().catch(() => null);
  return payload && typeof payload.message === "string" ? payload.message : fallback;
}

function featureEnabled(data: MonthlyBudgetsView, feature: string): boolean {
  return data.session.featureAccess.some((row) => row.feature === feature && row.enabled && !row.hidden);
}

export function MonthlyBudgetsWorkspace({ query }: { query: MonthlyBudgetQuery }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  // Send the caller's location along so Transactions can offer the way back
  // with the budget filters intact (Flask's workflow-return-strip).
  const returnTo = `${pathname}${searchParams.toString() ? `?${searchParams.toString()}` : ""}`;
  const [data, setData] = useState<MonthlyBudgetsView | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [refreshWarning, setRefreshWarning] = useState<string | null>(null);
  const [draggedCategoryId, setDraggedCategoryId] = useState<number | null>(null);

  const loadBudgets = useCallback(async () => {
    setLoading(true);
    setError(null);
    setRefreshWarning(null);
    try {
      const response = await fetch(apiRouteForQuery(query), { cache: "no-store" });
      if (response.status === 401) {
        router.replace(`/login?next=${encodeURIComponent(routeForQuery(query))}`);
        return;
      }
      if (response.status === 409) {
        router.replace("/onboarding");
        return;
      }
      if (!response.ok) throw new Error(await responseMessage(response, "We could not load your budgets."));
      const parsed = monthlyBudgetsViewSchema.safeParse(await response.json());
      if (!parsed.success) throw new Error("ClearPath returned invalid budget details.");
      setData(parsed.data);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "We could not load your budgets.");
    } finally {
      setLoading(false);
    }
  }, [query, router]);

  useEffect(() => { void loadBudgets(); }, [loadBudgets]);

  // Refresh live bank data after the page renders. Awaiting this before the
  // first fetch left the loading screen up for the whole Plaid sync, with no
  // timeout if it stalled.
  useEffect(() => {
    let cancelled = false;
    void refreshLiveBankData().then((result) => {
      if (cancelled) return;
      setRefreshWarning(result.warning);
      if (result.synced) void loadBudgets();
    });
    return () => { cancelled = true; };
  }, [loadBudgets]);


  const canEdit = data ? data.session.primaryAccountHolder || data.session.subject.householdRole === "editor" : false;
  const canMutate = Boolean(data && canEdit && !data.budgetHistoryMode);
  const activeRows = useMemo(() => data?.budgetSections.flatMap((section) => section.rows).filter((row) => row.categoryId !== null && row.categoryKind !== "income") ?? [], [data]);

  const navigate = (next: Partial<MonthlyBudgetQuery>) => {
    setNotice(null);
    router.push(routeForQuery({ ...query, ...next }));
  };

  const runMutation = async (key: string, path: string, options: RequestInit, success: string) => {
    setBusy(key);
    setError(null);
    setNotice(null);
    try {
      const response = await fetch(path, options);
      if (!response.ok) throw new Error(await responseMessage(response, "We could not save that budget change."));
      setNotice(success);
      await loadBudgets();
      return await response.json().catch(() => ({}));
    } catch (mutationError) {
      setError(mutationError instanceof Error ? mutationError.message : "We could not save that budget change.");
      return null;
    } finally {
      setBusy(null);
    }
  };

  const createBudget = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!data) return;
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const categoryLabel = String(form.get("categoryLabel") ?? "").trim();
    const monthlyTarget = Number(form.get("monthlyTarget"));
    const categoryKind = form.get("categoryKind") === "income" ? "income" : "expense";
    const result = await runMutation("create", "/api/budgets", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ categoryLabel, monthlyTarget, categoryKind, budgetMonth: data.budgetMonthValue }),
    }, `${categoryLabel || "Budget"} added.`);
    if (result) formElement.reset();
  };

  const saveAmount = async (event: FormEvent<HTMLFormElement>, row: BudgetRow) => {
    event.preventDefault();
    if (!data || !row.categoryId) return;
    const form = new FormData(event.currentTarget);
    await runMutation(`amount-${row.categoryId}`, `/api/budgets/${row.categoryId}`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ monthlyTarget: Number(form.get("monthlyTarget")), budgetMonth: data.budgetMonthValue }),
    }, `${row.category} updated.`);
  };

  const removeBudget = async (row: BudgetRow) => {
    if (!data || !row.categoryId || !window.confirm("Remove this budget category? Matching transactions will move to Other, and matching planning labels will be cleared.")) return;
    await runMutation(`delete-${row.categoryId}`, `/api/budgets/${row.categoryId}`, {
      method: "DELETE",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ budgetMonth: data.budgetMonthValue }),
    }, `${row.category} removed.`);
  };

  const activateSuggestion = async (row: BudgetRow) => {
    if (!data || !row.categoryId) return;
    await runMutation(`suggestion-${row.categoryId}`, `/api/budgets/${row.categoryId}`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ monthlyTarget: row.planned, budgetMonth: data.budgetMonthValue }),
    }, `${row.category} added to your active budgets.`);
  };

  const saveLayout = async (rows: Array<{ categoryId: number; groupKey: string }>) => {
    if (!data) return;
    await runMutation("layout", "/api/budgets/layout", {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ budgetMonth: data.budgetMonthValue, rows }),
    }, "Budget organization saved.");
  };

  const moveRow = async (categoryId: number, direction: -1 | 1) => {
    const index = activeRows.findIndex((row) => row.categoryId === categoryId);
    const target = index + direction;
    if (index < 0 || target < 0 || target >= activeRows.length) return;
    const reordered = [...activeRows];
    [reordered[index], reordered[target]] = [reordered[target], reordered[index]];
    await saveLayout(reordered.map((row) => ({ categoryId: row.categoryId as number, groupKey: row.groupKey })));
  };

  const changeGroup = async (categoryId: number, groupKey: string) => {
    await saveLayout(activeRows.map((row) => ({ categoryId: row.categoryId as number, groupKey: row.categoryId === categoryId ? groupKey : row.groupKey })));
  };

  const dropRow = async (event: DragEvent<HTMLElement>, targetRow: BudgetRow) => {
    event.preventDefault();
    if (!draggedCategoryId || draggedCategoryId === targetRow.categoryId) return;
    const from = activeRows.findIndex((row) => row.categoryId === draggedCategoryId);
    const to = activeRows.findIndex((row) => row.categoryId === targetRow.categoryId);
    if (from < 0 || to < 0) return;
    const reordered = [...activeRows];
    const [dragged] = reordered.splice(from, 1);
    reordered.splice(to, 0, { ...dragged, groupKey: targetRow.groupKey });
    setDraggedCategoryId(null);
    await saveLayout(reordered.map((row) => ({ categoryId: row.categoryId as number, groupKey: row.groupKey })));
  };

  const openLoanPlan = async (row: BudgetRow) => {
    if (!row.categoryId || !row.amortizationAction) return;
    if (row.amortizationAction.action === "open" && row.amortizationAction.fixedExpenseItemId) {
      router.push(`/loan-plans/${row.amortizationAction.fixedExpenseItemId}`);
      return;
    }
    setBusy(`loan-${row.categoryId}`);
    setError(null);
    try {
      const response = await fetch(`/api/budgets/${row.categoryId}/loan-plan`, { method: "POST" });
      if (!response.ok) throw new Error(await responseMessage(response, "We could not create that amortization schedule."));
      const payload = await response.json();
      router.push(`/loan-plans/${payload.fixedExpenseItemId}`);
    } catch (loanError) {
      setError(loanError instanceof Error ? loanError.message : "We could not create that amortization schedule.");
    } finally {
      setBusy(null);
    }
  };

  if (loading && !data) return <AuthenticatedPageFrame activePlanSection="budgets"><div className={styles.loadingPage}><span className="logo-mark">C</span><strong>Loading Budgets...</strong></div></AuthenticatedPageFrame>;
  if (!data) return <div className={styles.loadingPage}><div className={styles.loadError}><TriangleAlert size={24} aria-hidden="true" /><p>{error ?? "We could not load your budgets."}</p><button type="button" onClick={() => void loadBudgets()}>Try Again</button></div></div>;

  const firstActiveIndex = activeRows.length ? 0 : -1;
  const lastActiveIndex = activeRows.length - 1;

  return (
    <AuthenticatedPageFrame session={data.session} activePlanSection="budgets">
      <div className={styles.page}>
        <header className={styles.pageHeader}>
          <div><h1>Budgets</h1><p>{data.budgetMonthLabel} - Review budget history or adjust the current month.</p></div>
          <div className={styles.remainingPill} data-negative={data.totalBudgetRemaining < 0}>{signedCurrency(data.totalBudgetRemaining)} Expense Remaining</div>
        </header>

        <div className={styles.content}>
          {refreshWarning ? <div className={styles.warning}><TriangleAlert size={18} aria-hidden="true" />{refreshWarning}</div> : null}
          {error ? <div className={styles.error} role="alert"><TriangleAlert size={18} aria-hidden="true" />{error}</div> : null}
          {notice ? <div className={styles.notice} role="status">{notice}</div> : null}
          {busy ? <SavingIndicator /> : null}

          {data.onboardingComplete ? (
            <div className={styles.onboardingNotice}><div><strong>Your first budgets are started.</strong><span>Income is preset from setup, and categorized expenses create budget categories you can review and adjust here.</span></div><Link href={`/transactions?return_to=${encodeURIComponent(returnTo)}`}>Continue Categorizing</Link></div>
          ) : null}

          <section className={styles.toolbar} aria-label="Budget controls">
            <form className={styles.monthControl} onSubmit={(event) => { event.preventDefault(); const form = new FormData(event.currentTarget); navigate({ budgetMonth: String(form.get("budgetMonth") ?? "") }); }}>
              <label htmlFor="budget-month"><CalendarDays size={16} aria-hidden="true" />Month</label>
              <input id="budget-month" type="month" name="budgetMonth" defaultValue={data.budgetMonthValue} max={data.budgetCurrentMonth.slice(0, 7)} />
              <button type="submit">View</button>
              {data.budgetHistoryMode ? <button type="button" onClick={() => navigate({ budgetMonth: "" })}>Current Month</button> : null}
            </form>
            <div className={styles.segmented} aria-label="Budget layout">
              <button type="button" className={data.budgetView === "list" ? styles.selected : ""} aria-pressed={data.budgetView === "list"} onClick={() => navigate({ budgetView: "list" })}><LayoutList size={16} aria-hidden="true" />List</button>
              <button type="button" className={data.budgetView === "grouped" ? styles.selected : ""} aria-pressed={data.budgetView === "grouped"} onClick={() => navigate({ budgetView: "grouped" })}><Layers3 size={16} aria-hidden="true" />Major Categories</button>
            </div>
            <label className={styles.sortControl}>Sort<select aria-label="Sort budgets" value={data.budgetSort} onChange={(event) => navigate({ budgetSort: event.target.value })}>{Object.entries(data.budgetSortOptions).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>
          </section>

          {data.budgetHistoryMode ? <div className={styles.historyNotice}>This is a read-only historical budget. Current category changes do not rewrite {data.budgetMonthLabel}.</div> : null}

          <section className={styles.summaryBand} aria-label="Budget totals">
            <div><span>Expense Planned</span><strong>{currency(data.totalBudgetPlanned)}</strong></div>
            <div><span>Expense Spent</span><strong>{currency(data.totalBudgetActual)}</strong></div>
            <div><span>Expense Remaining</span><strong className={data.totalBudgetRemaining < 0 ? styles.negative : styles.positive}>{signedCurrency(data.totalBudgetRemaining)}</strong></div>
            <div><span>Expected Cash Flow</span><strong className={data.expectedCashFlow < 0 ? styles.negative : styles.positive}>{signedCurrency(data.expectedCashFlow)}</strong></div>
          </section>

          {canMutate ? (
            <details className={styles.addBudgetTool}>
              <summary><span><Plus size={17} aria-hidden="true" />Add Budget</span><ChevronRight size={17} aria-hidden="true" /></summary>
              <form onSubmit={(event) => void createBudget(event)}>
                <label>Category<input name="categoryLabel" list="budget-category-options" required placeholder="Choose or create a category" /></label>
                <datalist id="budget-category-options">{data.categoryLabelOptions.map((label) => <option value={label} key={label} />)}</datalist>
                <label>Monthly Budget<input name="monthlyTarget" type="number" min="0.01" step="0.01" required placeholder="0.00" /></label>
                <label>Type<select name="categoryKind" defaultValue="expense"><option value="expense">Expense</option><option value="income">Income</option></select></label>
                <button type="submit" disabled={busy === "create"}><Plus size={16} aria-hidden="true" />{busy === "create" ? "Adding..." : "Add Budget"}</button>
              </form>
            </details>
          ) : null}

          <div className={styles.budgetSheet}>
            {data.budgetSections.length === 0 ? <div className={styles.empty}>No category budgets yet.</div> : null}
            {data.budgetSections.map((section) => (
              <section className={styles.budgetSection} key={section.kind} aria-labelledby={`budget-section-${section.kind}`}>
                <div className={styles.sectionHeader}><div><h2 id={`budget-section-${section.kind}`}>{section.label}</h2><p>{section.description}</p></div><div><strong>{currency(section.actual)} / {currency(section.planned)}</strong>{section.transactionCount ? <Link href={`/transactions?ids=${section.transactionIds.join(",")}&return_to=${encodeURIComponent(returnTo)}`}>Review Transactions</Link> : null}</div></div>
                <div className={styles.tableHeader}><span>Category</span><span>Monthly Budget</span><span>Progress</span><span>Remaining</span></div>
                <div className={styles.rows}>
                  {section.rows.length === 0 ? <div className={styles.sectionEmpty}>{section.empty}</div> : section.rows.map((row) => {
                    const activeIndex = activeRows.findIndex((active) => active.categoryId === row.categoryId);
                    const canArrange = Boolean(canMutate && data.budgetDragEnabled && row.categoryId && row.categoryKind !== "income");
                    return (
                      <article className={styles.budgetRow} id={row.anchorId} key={`${section.kind}-${row.label}`} draggable={canArrange} onDragStart={() => setDraggedCategoryId(row.categoryId)} onDragOver={(event) => { if (canArrange) event.preventDefault(); }} onDrop={(event) => { if (canArrange) void dropRow(event, row); }}>
                        <div className={styles.nameCell}>
                          <div><strong>{row.category}</strong>{canArrange ? <GripVertical size={16} aria-label="Drag to reorder budget category" /> : null}</div>
                          <div className={styles.rowLinks}>
                            {row.transactionCount || row.categoryId ? <Link href={transactionHref(row)}>{row.transactionCount ? `Review ${row.transactionCount} Transaction${row.transactionCount === 1 ? "" : "s"}` : "Add Transactions"}</Link> : null}
                            {row.categoryKind === "income" && !data.budgetHistoryMode ? <Link href="/monthly-plan?section=baseline">{row.adjustLabel || "Adjust Income"}</Link> : null}
                            {row.amortizationAction && !data.budgetHistoryMode ? <button type="button" disabled={busy === `loan-${row.categoryId}`} onClick={() => void openLoanPlan(row)}>{row.amortizationAction.label}</button> : null}
                            {canMutate && row.canRemoveBudget ? <button type="button" className={styles.dangerLink} aria-label={`Remove ${row.category}`} disabled={busy === `delete-${row.categoryId}`} onClick={() => void removeBudget(row)}><Trash2 size={13} aria-hidden="true" />Remove</button> : null}
                          </div>
                          {canArrange ? <div className={styles.layoutControls}><button type="button" aria-label={`Move ${row.category} up`} disabled={busy === "layout" || activeIndex === firstActiveIndex} onClick={() => void moveRow(row.categoryId as number, -1)}><ArrowUp size={14} aria-hidden="true" /></button><button type="button" aria-label={`Move ${row.category} down`} disabled={busy === "layout" || activeIndex === lastActiveIndex} onClick={() => void moveRow(row.categoryId as number, 1)}><ArrowDown size={14} aria-hidden="true" /></button>{data.budgetGrouped ? <select aria-label={`Major category for ${row.category}`} value={row.groupKey} disabled={busy === "layout"} onChange={(event) => void changeGroup(row.categoryId as number, event.target.value)}>{data.budgetGroupOptions.map((group) => <option value={group.key} key={group.key}>{group.label}</option>)}</select> : null}</div> : null}
                        </div>
                        <div className={styles.amountCell}>{canMutate && row.categoryId ? <form onSubmit={(event) => void saveAmount(event, row)}><span>$</span><input aria-label={`Budget amount for ${row.category}`} name="monthlyTarget" type="number" min="0" step="0.01" defaultValue={row.planned.toFixed(2)} /><button type="submit" title={`Save ${row.category} budget`} aria-label={`Save ${row.category} budget`} disabled={busy === `amount-${row.categoryId}`}><Save size={15} aria-hidden="true" /></button></form> : <strong>{currency(row.planned)}</strong>}</div>
                        <div className={styles.progressCell}><div><span>{currency(row.actual)} {row.actualLabel}</span><span>{currency(row.planned)} {row.plannedLabel}</span></div><div className={styles.progressTrack}><span className={styles[row.progressStatus] ?? styles.ok} style={{ width: `${Math.min(Math.max(row.progressPercent, 0), 100)}%` }} /></div></div>
                        <div className={`${styles.remainingCell} ${row.remaining < 0 ? styles.negative : styles.positive}`}>{signedCurrency(row.remaining)}</div>
                      </article>
                    );
                  })}
                </div>
              </section>
            ))}

            {data.unassignedBudgetRows.length ? (
              <section className={`${styles.budgetSection} ${styles.cleanupSection}`} aria-labelledby="cleanup-title"><div className={styles.sectionHeader}><div><h2 id="cleanup-title">Other Spending To Categorize</h2><p>Categorize these transactions or add an active budget.</p></div><strong>{currency(data.unassignedBudgetRows.reduce((sum, row) => sum + row.actual, 0))} needs review</strong></div><div className={styles.tableHeader}><span>Category</span><span>Monthly Budget</span><span>Cleanup</span><span>Amount</span></div>{data.unassignedBudgetRows.map((row) => <article className={styles.budgetRow} key={row.anchorId}><div className={styles.nameCell}><strong>{row.category}</strong><div className={styles.rowLinks}><Link href={transactionHref(row)}>Review {row.transactionCount} Transaction{row.transactionCount === 1 ? "" : "s"}</Link></div></div><div className={styles.amountCell}>Not budgeted</div><div className={styles.progressCell}><div><span>{currency(row.actual)} needs review</span><span>Categorize or add a budget</span></div><div className={styles.progressTrack}><span className={styles.near} style={{ width: "100%" }} /></div></div><div className={`${styles.remainingCell} ${styles.negative}`}>{currency(row.actual)}</div></article>)}</section>
            ) : null}

            {data.suggestedBudgetSections.length && canMutate ? (
              <details className={styles.suggestions}><summary><span>Suggested Categories</span><span>Browse Suggestions</span></summary>{data.suggestedBudgetSections.map((section) => <div className={styles.suggestionGroup} key={section.kind}><h3>{section.label}</h3>{section.rows.map((row) => <div className={styles.suggestionRow} key={row.category}><div><strong>{row.category}</strong><span>{row.suggestionMatchCount} possible transaction{row.suggestionMatchCount === 1 ? "" : "s"} this month - Suggested {currency(row.planned)} / month</span></div><div>{row.transactionIds.length ? <Link href={transactionHref(row)}>Review Matches</Link> : null}<button type="button" disabled={busy === `suggestion-${row.categoryId}`} onClick={() => void activateSuggestion(row)}>Use</button></div></div>)}</div>)}</details>
            ) : null}
          </div>

          {!data.budgetHistoryMode && data.session.primaryAccountHolder && !featureEnabled(data, "subscriptions") ? <div className={styles.upgradeBand}><div><strong>Turn recurring budget categories into managed subscriptions.</strong><span>Upgrade to add subscription management and subscription analytics.</span></div><Link href="/select-plan">View Plans</Link></div> : null}
        </div>
      </div>
    </AuthenticatedPageFrame>
  );
}
