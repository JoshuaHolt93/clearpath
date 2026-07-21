"use client";

import { forecastBufferStatus } from "@clearpath/domain";
import { monthlyForecastViewSchema, type MonthlyForecastView } from "@clearpath/validation";
import { ArrowRight, CalendarRange, Pencil, Plus, Save, Trash2, TriangleAlert, X } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import { AuthenticatedShell } from "../authenticated-shell";
import { refreshLiveBankData } from "@/lib/live-bank-refresh";

import { SavingIndicator } from "../saving-indicator";
import styles from "./monthly-forecast.module.css";

type ForecastItem = MonthlyForecastView["forecastItems"][number];

function currency(value: number, decimals = 0): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(Math.abs(value));
}

function shortDate(value: string, includeYear = false): string {
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: includeYear ? "numeric" : undefined,
    timeZone: "UTC",
  }).format(new Date(`${value}T00:00:00Z`));
}

function featureEnabled(data: MonthlyForecastView, feature: string): boolean {
  return data.session.featureAccess.some((row) => row.feature === feature && row.enabled && !row.hidden);
}

function featurePlan(data: MonthlyForecastView, feature: string): string {
  return data.session.featureAccess.find((row) => row.feature === feature)?.requiredPlan ?? "an eligible plan";
}

function nullableString(form: FormData, name: string): string | null {
  return String(form.get(name) ?? "").trim() || null;
}

async function responseMessage(response: Response, fallback: string): Promise<string> {
  const body = await response.json().catch(() => null);
  return body && typeof body.message === "string" ? body.message : fallback;
}

function ForecastExpenseForm({
  data,
  item,
  busy,
  submitLabel,
  onSave,
  onDelete,
  categoryOptionsId,
}: {
  data: MonthlyForecastView;
  item?: ForecastItem;
  busy: boolean;
  submitLabel: string;
  onSave: (payload: Record<string, unknown>) => Promise<boolean>;
  onDelete?: () => Promise<void>;
  categoryOptionsId: string;
}) {
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const saved = await onSave({
      itemDate: nullableString(form, "itemDate"),
      description: nullableString(form, "description"),
      amount: Number(form.get("amount") ?? 0),
      itemType: "expense",
      categoryLabel: nullableString(form, "categoryLabel"),
      notes: nullableString(form, "notes"),
    });
    if (saved && !item) formElement.reset();
  };

  return (
    <form className={styles.expenseForm} onSubmit={submit}>
      <div className={styles.formGrid}>
        <label>Date<input name="itemDate" type="date" defaultValue={item?.itemDate ?? data.today} required /></label>
        <label>Description<input name="description" defaultValue={item?.description ?? ""} placeholder="Trip deposit, repair, tuition, annual bill..." required /></label>
        <label>Amount<input name="amount" type="number" inputMode="decimal" min="0.01" step="0.01" defaultValue={item?.amount ?? ""} required /></label>
        <label>Category Label
          <input name="categoryLabel" list={categoryOptionsId} defaultValue={item?.categoryLabel ?? ""} placeholder="Choose category" />
          <datalist id={categoryOptionsId}>{data.categoryLabelOptions.map((option) => <option key={option} value={option} />)}</datalist>
        </label>
      </div>
      <label>Notes<input name="notes" defaultValue={item?.notes ?? ""} placeholder="Optional context" /></label>
      <div className={styles.formActions}>
        <button type="submit" disabled={busy}><Save size={16} />{submitLabel}</button>
        {onDelete ? <button type="button" className={styles.deleteButton} disabled={busy} onClick={() => void onDelete()}><Trash2 size={16} />Delete</button> : null}
      </div>
    </form>
  );
}

function EditModal({ data, item, busy, onSave, onDelete, onClose }: {
  data: MonthlyForecastView;
  item: ForecastItem;
  busy: boolean;
  onSave: (payload: Record<string, unknown>) => Promise<boolean>;
  onDelete: () => Promise<void>;
  onClose: () => void;
}) {
  return (
    <div className={styles.modalShell} role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className={styles.modalPanel} role="dialog" aria-modal="true" aria-labelledby="forecast-edit-title">
        <header className={styles.modalHeader}>
          <div><h2 id="forecast-edit-title">Edit One-Time Forecast Item</h2><p>{item.description}</p></div>
          <button type="button" onClick={onClose} aria-label="Close"><X size={18} /></button>
        </header>
        <ForecastExpenseForm data={data} item={item} busy={busy} submitLabel="Save One-Time Item" onSave={onSave} onDelete={onDelete} categoryOptionsId={`forecast-edit-categories-${item.id}`} />
      </section>
    </div>
  );
}

export function MonthlyForecastWorkspace() {
  const router = useRouter();
  const [data, setData] = useState<MonthlyForecastView | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [refreshWarning, setRefreshWarning] = useState<string | null>(null);
  const [editing, setEditing] = useState<ForecastItem | null>(null);

  const loadForecast = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch("/api/monthly-plan?section=forecast", { cache: "no-store" });
      if (response.status === 401) { router.replace("/login?next=%2Fmonthly-plan%3Fsection%3Dforecast"); return; }
      if (response.status === 409) { router.replace("/onboarding"); return; }
      if (!response.ok) throw new Error(await responseMessage(response, "We could not load the three-month forecast."));
      const parsed = monthlyForecastViewSchema.safeParse(await response.json());
      if (!parsed.success) throw new Error("ClearPath returned invalid forecast details.");
      setData(parsed.data);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "We could not load the three-month forecast.");
    } finally {
      setLoading(false);
    }
  }, [router]);

  useEffect(() => { void loadForecast(); }, [loadForecast]);

  // Refresh live bank data *after* the page is on screen. This used to run
  // before the first fetch, so a slow Plaid sync left the loading screen up
  // indefinitely with no timeout.
  useEffect(() => {
    let cancelled = false;
    void refreshLiveBankData().then((result) => {
      if (cancelled) return;
      setRefreshWarning(result.warning);
      if (result.synced) void loadForecast();
    });
    return () => { cancelled = true; };
  }, [loadForecast]);

  const canEdit = data ? data.session.primaryAccountHolder || data.session.subject.householdRole === "editor" : false;
  const expenseItems = useMemo(
    () => data?.forecastItems.filter((item) => item.itemType === "expense") ?? [],
    [data],
  );

  const mutateItem = async (key: string, path: string, options: RequestInit, success: string): Promise<boolean> => {
    setBusy(key);
    setError(null);
    setNotice(null);
    try {
      const response = await fetch(path, options);
      if (!response.ok) throw new Error(await responseMessage(response, "We could not save that forecast item."));
      setNotice(success);
      setEditing(null);
      await loadForecast();
      return true;
    } catch (mutationError) {
      setError(mutationError instanceof Error ? mutationError.message : "We could not save that forecast item.");
      return false;
    } finally {
      setBusy(null);
    }
  };

  const saveNew = (payload: Record<string, unknown>) => mutateItem(
    "create",
    "/api/forecast-items",
    { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(payload) },
    "One-time expense added.",
  );

  const saveEditing = (payload: Record<string, unknown>) => editing
    ? mutateItem(
        `edit-${editing.id}`,
        `/api/forecast-items/${editing.id}`,
        { method: "PATCH", headers: { "content-type": "application/json" }, body: JSON.stringify(payload) },
        "One-time forecast item updated.",
      )
    : Promise.resolve(false);

  const deleteEditing = async () => {
    if (!editing || !window.confirm("Delete this one-time forecast item?")) return;
    await mutateItem(
      `delete-${editing.id}`,
      `/api/forecast-items/${editing.id}`,
      { method: "DELETE", headers: { "content-type": "application/json" }, body: JSON.stringify({ confirm: true }) },
      "One-time forecast item removed.",
    );
  };

  if (loading && !data) return <div className={styles.loadingPage}><span className="logo-mark">C</span><strong>Loading 3-Month Forecast...</strong></div>;
  if (!data) return <div className={styles.loadingPage}><div className={styles.loadError}><TriangleAlert size={24} /><p>{error ?? "We could not load the three-month forecast."}</p><button type="button" onClick={() => void loadForecast()}>Try Again</button></div></div>;

  const cashProjection = featureEnabled(data, "cash_projection");
  const requiredPlan = featurePlan(data, "cash_projection");

  return (
    <AuthenticatedShell session={data.session} activePlanSection="forecast">
      <div className={styles.page}>
        <header className={styles.pageHeader}>
          <div><h1>3-Month Forecast</h1><p>Look ahead across the next three months, then use cash balance projections when timing needs more precision.</p></div>
          <div className={styles.horizonPill}><CalendarRange size={16} />Rolling 3 Months</div>
        </header>

        <div className={styles.content}>
          {refreshWarning ? <div className={styles.warning}><TriangleAlert size={18} />{refreshWarning}</div> : null}
          {error ? <div className={styles.error} role="alert"><TriangleAlert size={18} />{error}</div> : null}
          {notice ? <div className={styles.notice} role="status">{notice}</div> : null}
          {busy ? <SavingIndicator /> : null}
          {!canEdit ? <div className={styles.viewerBand}>You have view-only household access. Forecast items are read-only.</div> : null}

          {!cashProjection ? (
            <section className={styles.upgradeBand}>
              <div><strong>Want the day-by-day version?</strong><p>{requiredPlan} unlocks Cash Balance Projections with calendar, list, and graph views.</p></div>
              <Link href="/settings/billing">Upgrade To {requiredPlan}<ArrowRight size={15} /></Link>
            </section>
          ) : null}

          <section className={styles.forecastPanel} id="quick-forecast">
            <header className={styles.sectionHeader}>
              <div><h2>Rolling Forecast</h2><p>Income, expenses, cash flow, and planned movement from the current plan.</p></div>
              <div className={styles.sectionActions}>
                <a href="#forecast-expenses"><Plus size={15} />Plan One-Time Expense</a>
                <Link href={cashProjection ? "/cash-projections" : "/settings/billing"}>{cashProjection ? "Open Cash Balance Projections" : "Upgrade For Cash Projections"}<ArrowRight size={15} /></Link>
              </div>
            </header>

            <div className={styles.monthGrid}>
              {data.forecastMonths.map((month) => {
                const status = forecastBufferStatus(month.plannedBuffer);
                const visibleItems = month.forecastItems.slice(0, 5);
                const extraItems = month.forecastItems.slice(5);
                return (
                  <article className={styles.monthCard} key={month.monthStart}>
                    <header><h3>{month.monthName}</h3><span className={styles[status.key]}><i />{status.label}</span></header>
                    <div className={styles.metrics}>
                      <div><span>Income</span><strong>{currency(month.forecastIncomeTotal)}</strong></div>
                      <div><span>Expenses</span><strong>{currency(month.forecastExpenseTotal)}</strong></div>
                      <div><span>Cash Flow</span><strong data-negative={month.plannedBuffer < 0}>{month.plannedBuffer < 0 ? "-" : ""}{currency(month.plannedBuffer)}</strong></div>
                      <div><span>Ending Cash</span><strong data-negative={month.endingCash < 0}>{month.endingCash < 0 ? "-" : ""}{currency(month.endingCash)}</strong></div>
                    </div>
                    <div className={styles.movements}>
                      <h4>Planned Movement</h4>
                      {visibleItems.map((item, index) => (
                        <div key={`${item.source}-${item.sourceId ?? index}-${item.date}`}><span>{shortDate(item.date)} - {item.description}</span><strong data-income={item.itemType === "income"}>{item.itemType === "income" ? "+" : "-"}{currency(item.amount)}</strong></div>
                      ))}
                      {extraItems.length ? (
                        <details><summary>+ {extraItems.length} more planned item{extraItems.length === 1 ? "" : "s"}</summary>{extraItems.map((item, index) => <div key={`${item.source}-${item.sourceId ?? index}-${item.date}`}><span>{shortDate(item.date)} - {item.description}</span><strong data-income={item.itemType === "income"}>{item.itemType === "income" ? "+" : "-"}{currency(item.amount)}</strong></div>)}</details>
                      ) : null}
                      {!month.forecastItems.length ? <p>No scheduled items yet. Categorize transactions and mark recurring expenses to build this out.</p> : null}
                    </div>
                  </article>
                );
              })}
            </div>
          </section>

          <section className={styles.expenseSection} id="forecast-expenses">
            <header className={styles.sectionHeader}><div><h2>Plan One-Time Expense</h2><p>Add an expected expense and review the one-time items already feeding the forecast.</p></div><span className={styles.countPill}>{expenseItems.length} Total</span></header>
            {canEdit ? <ForecastExpenseForm data={data} busy={busy === "create"} submitLabel="Add One-Time Expense" onSave={saveNew} categoryOptionsId="forecast-create-categories" /> : null}
            <div className={styles.expenseList}>
              <div className={styles.listHeader}><span>Date</span><span>Description</span><span>Category</span><span>Amount</span><span /></div>
              {expenseItems.map((item) => (
                <div className={styles.expenseRow} key={item.id}>
                  <span>{shortDate(item.itemDate, true)}</span>
                  <strong>{item.description}</strong>
                  <span>{item.categoryLabel ?? "-"}</span>
                  <strong className={styles.expenseAmount}>-{currency(item.amount, 2)}</strong>
                  {canEdit ? <button type="button" onClick={() => setEditing(item)}><Pencil size={14} />Edit</button> : <span />}
                </div>
              ))}
              {!expenseItems.length ? <div className={styles.empty}>Add one-time expected bills, repairs, annual renewals, or travel costs here.</div> : null}
            </div>
          </section>

          <nav className={styles.footerLinks} aria-label="Monthly plan sections"><Link href="/monthly-plan?section=tools">Quick Planning</Link><Link href="/monthly-plan?section=budgets">Budgets</Link></nav>
        </div>
      </div>

      {editing ? <EditModal data={data} item={editing} busy={Boolean(busy)} onSave={saveEditing} onDelete={deleteEditing} onClose={() => setEditing(null)} /> : null}
    </AuthenticatedShell>
  );
}
