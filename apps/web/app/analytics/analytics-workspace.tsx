"use client";

import { analyticsViewSchema, type AnalyticsSnapshotView, type AnalyticsSummaryView, type AnalyticsView } from "@clearpath/validation";
import { BarChart3, Bot, RefreshCw, Sparkles } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useCallback, useEffect, useState } from "react";

import { AuthenticatedShell } from "../authenticated-shell";
import styles from "./analytics.module.css";

export type AnalyticsQuery = { range: string; endMonth: string; historyRange: string; historyEndMonth: string };

const currency = (value: number) => new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(value);
const percent = (value: number, maximum: number) => `${Math.min(maximum > 0 ? Math.abs(value) / maximum * 100 : 0, 100)}%`;
const dateLabel = (value: string, format: "short" | "long" = "short") => new Date(`${value}T12:00:00`).toLocaleDateString("en-US", format === "long" ? { month: "long", year: "numeric" } : { month: "short", year: "numeric" });
const monthValue = (value: string) => value.slice(0, 7);

async function responseMessage(response: Response, fallback: string) {
  const body = await response.json().catch(() => null) as { message?: string } | null;
  return body?.message || fallback;
}

function queryString(query: AnalyticsQuery) {
  const params = new URLSearchParams({ range: query.range, history_range: query.historyRange });
  if (query.endMonth) params.set("end_month", query.endMonth);
  if (query.historyEndMonth) params.set("history_end_month", query.historyEndMonth);
  return params.toString();
}

export function AnalyticsWorkspace({ query }: { query: AnalyticsQuery }) {
  const router = useRouter();
  const [data, setData] = useState<AnalyticsView | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      const response = await fetch(`/api/analytics?${queryString(query)}`, { cache: "no-store" });
      if (!response.ok) throw new Error(await responseMessage(response, "We could not load analytics."));
      const parsed = analyticsViewSchema.safeParse(await response.json());
      if (!parsed.success) throw new Error("Analytics data did not match the expected contract.");
      setData(parsed.data);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "We could not load analytics.");
    }
  }, [query]);

  useEffect(() => { void load(); }, [load]);

  const submitPrimary = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    router.push(`/analytics?${queryString({
      range: String(form.get("range") ?? "month"),
      endMonth: String(form.get("end_month") ?? ""),
      historyRange: data?.selectedHistoryRange ?? query.historyRange,
      historyEndMonth: monthValue(data?.historyEndMonth ?? query.historyEndMonth),
    })}`);
  };

  const submitHistory = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    router.push(`/analytics?${queryString({
      range: data?.selectedRange ?? query.range,
      endMonth: monthValue(data?.endMonth ?? query.endMonth),
      historyRange: String(form.get("history_range") ?? "quarter"),
      historyEndMonth: String(form.get("history_end_month") ?? ""),
    })}`);
  };

  const content = <main className={styles.page}>
    <header className={styles.pageHeader}>
      <div><p className={styles.eyebrow}>Financial Trends</p><h1>Analytics</h1><p>Monthly budget history, spending trends, cash flow, income patterns, and subscription impact.</p></div>
      {data ? <form className={styles.filter} onSubmit={submitPrimary}>
        <label><span>Range</span><select name="range" defaultValue={data.selectedRange}>{Object.entries(data.rangeOptions).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
        <label><span>Ending Month</span><input type="month" name="end_month" defaultValue={monthValue(data.endMonth)} /></label>
        <button type="submit">Apply</button>
      </form> : null}
    </header>

    {error ? <div className={styles.error} role="alert"><span>{error}</span><button type="button" onClick={() => void load()}>Try Again</button></div> : null}
    {!data && !error ? <div className={styles.loading}><RefreshCw className={styles.spin} size={20} />Loading analytics...</div> : null}

    {data ? <div className={styles.content}>
      <SummaryStats data={data} />
      {!data.aiCoachHidden ? <AiLens enabled={data.aiCoachEnabled} /> : null}
      <section className={styles.chartGrid}>
        <HistoryChart title="Income History" badge={`${dateLabel(data.summary.startDate)} - ${dateLabel(data.summary.endDate)}`} summary={data.summary} kind="income" />
        <HistoryChart title="Spending History" badge={`${data.summary.snapshots.length} Month${data.summary.snapshots.length === 1 ? "" : "s"}`} summary={data.summary} kind="spending" />
        <HistoryChart title="Cash Flow History" badge="Income Minus Spending" summary={data.summary} kind="cash-flow" />
        <CategoryPanel summary={data.summary} />
      </section>
      <SubscriptionPanel data={data} />
      <BudgetHistory data={data} onSubmit={submitHistory} />
    </div> : null}
  </main>;

  return data ? <AuthenticatedShell session={data.session}>{content}</AuthenticatedShell> : content;
}

function SummaryStats({ data }: { data: AnalyticsView }) {
  const summary = data.summary;
  const single = data.selectedRange === "month";
  const cashClass = summary.totalNetCashFlow > 0 ? styles.positive : summary.totalNetCashFlow < 0 ? styles.negative : "";
  const expectedClass = summary.totalExpectedCashFlow > 0 ? styles.positive : summary.totalExpectedCashFlow < 0 ? styles.negative : "";
  const dtiClass = data.debtToIncomeRatio >= .43 ? styles.negative : data.debtToIncomeRatio < .36 ? styles.positive : styles.neutral;
  return <section className={styles.stats} aria-label="Analytics summary">
    <article><span>Income History</span><strong>{currency(summary.totalIncome)}</strong><small>{single ? `Income In ${dateLabel(data.endMonth, "long")}` : `${currency(summary.averageIncome)} Average Per Month`}</small></article>
    <article><span>Spending History</span><strong>{currency(summary.totalSpending)}</strong><small>{single ? `Spending In ${dateLabel(data.endMonth, "long")}` : `${currency(summary.averageSpending)} Average Per Month`}</small></article>
    <article><span>Cash Flow History</span><strong className={cashClass}>{currency(summary.totalNetCashFlow)}</strong><small>{single ? `${summary.totalNetCashFlow >= 0 ? "Surplus" : "Shortfall"} In ${dateLabel(data.endMonth, "long")}` : `${currency(Math.abs(summary.averageNetCashFlow))} Average Monthly ${summary.averageNetCashFlow >= 0 ? "Surplus" : "Shortfall"}`}</small></article>
    <article><span>Budgeted Cash Flow</span><strong className={expectedClass}>{currency(summary.totalExpectedCashFlow)}</strong><small>{single ? `Expected For ${dateLabel(data.endMonth, "long")}` : `Expected Across ${summary.rangeLabel}`}</small></article>
    <article><span>Debt-To-Income Ratio</span><strong className={dtiClass}>{Math.round(data.debtToIncomeRatio * 100)}%</strong><small>Loan payments vs planned monthly income</small></article>
  </section>;
}

function AiLens({ enabled }: { enabled: boolean }) {
  const prompt = "Help me understand the biggest patterns in this Analytics page: income, spending, cash flow, debt-to-income, subscriptions, and category movement. Point out what looks worth reviewing next.";
  return <section className={styles.aiPanel}>
    <div><p className={styles.panelKicker}><Bot size={15} />Premier AI Analytics Lens</p><h2>{enabled ? "Turn trends into the next useful review." : "Have ClearPath explain the patterns behind the numbers."}</h2><p>Review budget drift, cash-flow swings, subscriptions, DTI, and category movement with educational coaching that does not provide investment, tax, or legal advice.</p></div>
    {enabled ? <button type="button" className={styles.aiButton} onClick={() => window.dispatchEvent(new CustomEvent("clearpath:open-ai-coach", { detail: { prompt, autoRun: true } }))}><Sparkles size={16} />Ask AI Coach</button> : <Link href="/select-plan" className={styles.aiButton}>Upgrade To Premier</Link>}
  </section>;
}

function HistoryChart({ title, badge, summary, kind }: { title: string; badge: string; summary: AnalyticsSummaryView; kind: "income" | "spending" | "cash-flow" }) {
  const maximum = kind === "income" ? summary.maxIncome : kind === "spending" ? summary.maxSpending : summary.maxCashFlow;
  const values = (row: AnalyticsSnapshotView) => kind === "income"
    ? { planned: row.plannedIncome, actual: row.actualIncome }
    : kind === "spending"
      ? { planned: row.plannedFixedExpenses + row.plannedVariableExpenses + row.plannedTaxes, actual: row.actualTotalExpenses }
      : { planned: row.expectedCashFlow, actual: row.netCashFlow };
  return <section className={styles.panel}>
    <header><h2>{title}</h2><span>{badge}</span></header>
    <div className={styles.bars}>{summary.snapshots.map((row) => { const amounts = values(row); return <div className={styles.barRow} key={row.month}>
      <time>{new Date(`${row.month}T12:00:00`).toLocaleDateString("en-US", { month: "short" })}</time>
      <div className={styles.barTrack}><i style={{ width: percent(amounts.planned, maximum) }} /><b className={kind === "spending" || (kind === "cash-flow" && amounts.actual < 0) ? styles.spendingBar : styles.incomeBar} style={{ width: percent(amounts.actual, maximum) }} /></div>
      <strong className={kind === "cash-flow" && amounts.actual < 0 ? styles.negative : ""}>{currency(amounts.actual)}</strong>
    </div>; })}</div>
    <footer><span><i className={styles.plannedDot} />{kind === "cash-flow" ? "Expected" : "Planned"}</span><span><i className={styles.actualDot} />Actual</span></footer>
  </section>;
}

function CategoryPanel({ summary }: { summary: AnalyticsSummaryView }) {
  return <section className={styles.panel}>
    <header><h2>Spending By Category</h2><Link href="/transactions">Review Transactions</Link></header>
    <div className={styles.categoryList}>{summary.categoryRows.length ? summary.categoryRows.map((row) => <div className={styles.categoryRow} key={`${row.categoryId}-${row.category}`}>
      <span>{row.category}</span><div><i style={{ width: percent(row.amount, summary.totalSpending) }} /></div><strong>{currency(row.amount)}</strong><small>{summary.totalSpending ? Math.round(row.amount / summary.totalSpending * 100) : 0}%</small>
    </div>) : <Empty text="No spending data for this period yet." />}</div>
  </section>;
}

function SubscriptionPanel({ data }: { data: AnalyticsView }) {
  const subscriptions = data.summary.subscriptions;
  if (!data.subscriptionAnalyticsEnabled) return <section className={styles.upgradePanel}><div><p className={styles.panelKicker}>Subscription Analytics</p><h2>See subscription impact after you upgrade.</h2><p>{data.subscriptionAnalyticsPlanLabel} unlocks upcoming charges, service mix, and savings-opportunity review.</p></div><Link href="/select-plan">Upgrade To {data.subscriptionAnalyticsPlanLabel}</Link></section>;
  return <section className={styles.panel}>
    <header><h2>Subscriptions Analytics</h2><div className={styles.linkRow}><Link href="/subscriptions">Manage Subscriptions</Link><Link href="/transactions">Review Transactions</Link></div></header>
    {!subscriptions.activeCount ? <Empty title="No Subscription Analytics Yet" text="Scan or mark Consumer Subscription transactions to see monthly impact, upcoming charges, and savings opportunities here." link="/subscriptions" /> : <div className={styles.subscriptionBody}>
      <div className={styles.subscriptionStats}><article><span>Monthly Subscription Spend</span><strong>{currency(subscriptions.monthlyTotal)}</strong><small>{subscriptions.activeCount} active or review items</small></article><article><span>Annualized Impact</span><strong>{currency(subscriptions.annualTotal)}</strong><small>If the current monthly mix continues</small></article><article><span>Recurring Spending Mix</span><strong>{subscriptions.spendingShare}%</strong><small>Of average monthly spending</small></article><article><span>Needs Review</span><strong>{subscriptions.reviewCount}</strong><small>Review-ready or cancellation-in-progress</small></article></div>
      <div className={styles.subscriptionGrid}>
        <section><h3>Service Mix</h3>{subscriptions.categoryBreakdown.length ? subscriptions.categoryBreakdown.map((row) => <div className={styles.mixRow} key={row.category}><span>{row.category}<b>{currency(row.amount)} <small>{row.percent}%</small></b></span><div><i style={{ width: `${Math.min(row.percent, 100)}%` }} /></div></div>) : <p>No subscription category mix yet.</p>}</section>
        <section><h3>Upcoming Charges</h3>{subscriptions.upcoming.length ? subscriptions.upcoming.map((row) => <div className={styles.compactRow} key={row.id}><span><strong>{row.name}</strong><small>{row.nextChargeDate ? new Date(`${row.nextChargeDate}T12:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric" }) : "Date not set"} - {row.cycle}</small></span><b>{currency(row.monthlyAmount)}</b></div>) : <p>No upcoming subscription charges found.</p>}</section>
        <section><h3>Savings Opportunities</h3>{subscriptions.opportunities.length ? subscriptions.opportunities.map((row) => <div className={styles.compactRow} key={row.subscription.id}><span><strong>{row.subscription.name}</strong><small>{row.reason}</small></span><b>{currency(row.subscription.monthlyAmount)}</b></div>) : <p>No subscription savings opportunities flagged yet.</p>}</section>
      </div>
    </div>}
  </section>;
}

function BudgetHistory({ data, onSubmit }: { data: AnalyticsView; onSubmit(event: FormEvent<HTMLFormElement>): void }) {
  return <section className={styles.panel}>
    <header className={styles.historyHeader}><div><h2>Monthly Budget History</h2><p>Defaults to the trailing 3 months, separate from the Analytics range above.</p></div><form className={styles.historyFilter} onSubmit={onSubmit}><select name="history_range" aria-label="Budget History Range" defaultValue={data.selectedHistoryRange}>{Object.entries(data.rangeOptions).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select><input type="month" name="history_end_month" aria-label="Budget History Ending Month" defaultValue={monthValue(data.historyEndMonth)} /><button type="submit">Apply</button></form></header>
    <div className={styles.tableWrap}><table><thead><tr><th>Month</th><th>Planned Income</th><th>Actual Income</th><th>Planned Spending</th><th>Actual Spending</th><th>Budget Remaining</th><th>Expected Cash Flow</th><th>Net Cash Flow</th></tr></thead><tbody>{[...data.budgetHistorySummary.snapshots].reverse().map((row) => <tr key={row.month}><td>{dateLabel(row.month, "long")}</td><td>{currency(row.plannedIncome)}</td><td>{currency(row.actualIncome)}</td><td>{currency(row.plannedFixedExpenses + row.plannedVariableExpenses + row.plannedTaxes)}</td><td>{currency(row.actualTotalExpenses)}</td><td>{currency(row.budgetRemaining)}</td><td>{currency(row.expectedCashFlow)}</td><td className={row.netCashFlow > 0 ? styles.positive : row.netCashFlow < 0 ? styles.negative : ""}>{currency(row.netCashFlow)}</td></tr>)}</tbody></table></div>
  </section>;
}

function Empty({ title, text, link }: { title?: string; text: string; link?: string }) {
  return <div className={styles.empty}><BarChart3 size={22} /><strong>{title}</strong><p>{text}</p>{link ? <Link href={link}>Open Subscriptions</Link> : null}</div>;
}
