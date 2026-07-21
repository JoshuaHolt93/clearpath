"use client";

import { dashboardViewSchema, type DashboardView } from "@clearpath/validation";
import {
  AlertTriangle,
  ArrowRight,
  CircleCheck,
  Info,
  Sparkles,
  Trash2,
  TrendingUp,
  Upload,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import { AuthenticatedShell } from "../authenticated-shell";
import { refreshLiveBankData } from "@/lib/live-bank-refresh";
import styles from "./dashboard.module.css";

function currency(value: number, decimals = 0): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: decimals,
    minimumFractionDigits: decimals,
  }).format(Math.abs(value));
}

function signedCurrency(value: number, decimals = 0): string {
  return `${value < 0 ? "-" : ""}${currency(value, decimals)}`;
}

function dateLabel(value: string, options: Intl.DateTimeFormatOptions): string {
  return new Intl.DateTimeFormat("en-US", { ...options, timeZone: "UTC" }).format(new Date(`${value}T00:00:00Z`));
}

function guidanceTarget(target: string): string {
  const paths: Record<string, string> = {
    dashboard: "/dashboard",
    monthly_plan_forecast: "/monthly-plan?section=forecast",
    cash_projections: "/cash-projections",
    subscriptions: "/subscriptions",
    monthly_plan_budgets: "/monthly-plan?section=budgets",
    goals: "/goals",
    retirement_plan: "/retirement-plan",
  };
  return paths[target] ?? "/dashboard";
}

async function responseMessage(response: Response, fallback: string): Promise<string> {
  const payload = await response.json().catch(() => null);
  return payload && typeof payload.message === "string" ? payload.message : fallback;
}

function FeatureTile({ title, body, action, href, badge, upgrade = false }: {
  title: string;
  body: string;
  action: string;
  href: string;
  badge?: string;
  upgrade?: boolean;
}) {
  return (
    <Link href={href} className={`${styles.setupTile} ${upgrade ? styles.upgradeTile : ""}`}>
      <div>
        <div className={styles.setupTitle}>{title}{badge ? <span>{badge}</span> : null}</div>
        <p>{body}</p>
      </div>
      <strong>{action}<ArrowRight size={15} aria-hidden="true" /></strong>
    </Link>
  );
}

function PlanTable({ data }: { data: DashboardView }) {
  return (
    <section className={styles.panel} aria-labelledby="plan-title">
      <div className={styles.panelHeader}>
        <div><h2 id="plan-title">Current Month Plan vs Actual</h2><p>Planned amounts compared with recorded activity.</p></div>
        <Link href="/monthly-plan?section=tools" className={styles.textLink}>Open Plan</Link>
      </div>
      <div className={styles.planBody}>
        <div className={`${styles.planRow} ${styles.planHeader}`}><span>Category</span><span>Plan</span><span>Actual</span><span>Diff</span></div>
        {data.planRows.map((row) => {
          const difference = row.actual - row.planned;
          const content = <div className={styles.planRow}><strong>{row.label}</strong><span>{currency(row.planned)}</span><span>{currency(row.actual)}</span><span className={difference > 0 && row.type !== "income" ? styles.negative : difference < 0 && row.type !== "income" ? styles.positive : ""}>{difference === 0 ? "-" : signedCurrency(difference)}</span></div>;
          return row.details.length ? (
            <details className={styles.planDetails} key={row.label}>
              <summary>{content}</summary>
              <div className={styles.detailRows}>{row.details.map((detail, index) => {
                const detailDifference = detail.actual - detail.planned;
                return <div className={`${styles.planRow} ${styles.detailRow}`} key={`${detail.label}-${index}`}><span>{detail.label}</span><span>{currency(detail.planned)}</span><span>{currency(detail.actual)}</span><span>{detailDifference === 0 ? "-" : signedCurrency(detailDifference)}</span></div>;
              })}</div>
            </details>
          ) : <div key={row.label}>{content}</div>;
        })}
        <div className={styles.planSummary}>
          <div><span>Budget Remaining for the Month</span><strong className={data.budgetRemaining < 0 ? styles.negative : ""}>{signedCurrency(data.budgetRemaining)}</strong></div>
          <div><span>Expected Cash Flow</span><strong className={data.expectedCashFlow < 0 ? styles.negative : styles.positive}>{signedCurrency(data.expectedCashFlow)}</strong></div>
        </div>
      </div>
    </section>
  );
}

export function DashboardWorkspace({ initialWelcome }: { initialWelcome: boolean }) {
  const router = useRouter();
  const [data, setData] = useState<DashboardView | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshWarning, setRefreshWarning] = useState<string | null>(null);
  const [deletingGoalId, setDeletingGoalId] = useState<number | null>(null);

  const loadDashboard = useCallback(async () => {
    setLoading(true);
    setError(null);
    setRefreshWarning(null);
    try {
      const response = await fetch(`/api/dashboard${initialWelcome ? "?welcome=1" : ""}`, { cache: "no-store" });
      if (response.status === 401) {
        router.replace("/login?next=/dashboard");
        return;
      }
      if (response.status === 403) {
        router.replace("/onboarding");
        return;
      }
      if (!response.ok) throw new Error(await responseMessage(response, "We could not load your dashboard."));
      const parsed = dashboardViewSchema.safeParse(await response.json());
      if (!parsed.success) throw new Error("ClearPath returned invalid dashboard details.");
      setData(parsed.data);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "We could not load your dashboard.");
    } finally {
      setLoading(false);
    }
  }, [initialWelcome, router]);

  useEffect(() => { void loadDashboard(); }, [loadDashboard]);

  // Live bank refresh runs after the dashboard is on screen; blocking the
  // first render on a Plaid sync could hang the page with no timeout.
  useEffect(() => {
    let cancelled = false;
    void refreshLiveBankData().then((result) => {
      if (cancelled) return;
      setRefreshWarning(result.warning);
      if (result.synced) void loadDashboard();
    });
    return () => { cancelled = true; };
  }, [loadDashboard]);

  const canEdit = data ? data.session.primaryAccountHolder || data.session.subject.householdRole === "editor" : false;
  const greeting = useMemo(() => {
    const hour = new Date().getUTCHours();
    return hour < 12 ? "morning" : hour < 17 ? "afternoon" : "evening";
  }, []);

  const deleteGoal = async (goalId: number) => {
    if (!window.confirm("Delete this goal?")) return;
    setDeletingGoalId(goalId);
    setError(null);
    try {
      const response = await fetch(`/api/goals/${goalId}`, { method: "DELETE" });
      if (!response.ok) throw new Error(await responseMessage(response, "We could not delete that goal."));
      setData((current) => current ? { ...current, goals: current.goals.filter((goal) => goal.id !== goalId) } : current);
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : "We could not delete that goal.");
    } finally {
      setDeletingGoalId(null);
    }
  };

  if (loading && !data) {
    return <main className={styles.loadingPage}><span className="logo-mark">C</span><strong>Loading Today...</strong></main>;
  }
  if (!data) {
    return <main className={styles.loadingPage}><div className={styles.loadError} role="alert"><strong>Dashboard Unavailable</strong><p>{error}</p><button type="button" onClick={() => void loadDashboard()}>Try Again</button></div></main>;
  }

  const cashFeature = data.session.featureAccess.find((row) => row.feature === "cash_projection");
  const retirementFeature = data.session.featureAccess.find((row) => row.feature === "retirement_planning");
  const statusLabel = data.metrics.onTrackStatus === "green" ? "On Track" : data.metrics.onTrackStatus === "yellow" ? "Watch Spending" : "Over Pace";
  const maxCategory = Math.max(data.metrics.variableSpend, ...data.categoryTotals.map((row) => row.amount), 1);

  return (
    <AuthenticatedShell session={data.session}>
      <div className={styles.page}>
        <header className={styles.pageHeader}>
          <div><h1>Good {greeting}, {data.session.subject.firstName}</h1><p>{data.monthName} - Day {data.elapsedDays} of {data.totalDays}</p></div>
          <div className={styles.headerActions}>
            <span className={`${styles.statusPill} ${styles[data.metrics.onTrackStatus]}`}><span />{statusLabel}</span>
            <Link href="/transactions?import=csv" className={styles.secondaryButton}><Upload size={16} aria-hidden="true" />Import CSV</Link>
          </div>
        </header>

        <div className={styles.content}>
          {refreshWarning ? <div className={styles.warning} role="alert"><AlertTriangle size={18} aria-hidden="true" /><span>{refreshWarning}</span></div> : null}
          {error ? <div className={styles.error} role="alert"><AlertTriangle size={18} aria-hidden="true" /><span>{error}</span></div> : null}

          {data.showTutorial ? (
            <section className={styles.tutorial} aria-labelledby="tutorial-title">
              <div className={styles.panelHeader}><div><h2 id="tutorial-title">Welcome To Today</h2><p>A quick orientation for reading ClearPath without learning everything at once.</p></div><Link href="/help" className={styles.secondaryButton}>Open Help</Link></div>
              <div className={styles.tutorialSteps}>
                <div><span>1</span><p><strong>Start With The Month</strong>Month Progress and Current Month Plan vs Actual show whether the month is on pace.</p></div>
                <div><span>2</span><p><strong>Clean Up Transactions</strong>Review Transactions powers Budgets and Analytics, so categorize anything still sitting in Other.</p></div>
                <div><span>3</span><p><strong>Use Help Any Time</strong>Short guides cover Today, Budgets, Quick Planning, Rules, Analytics, Goals, and Settings.</p></div>
              </div>
              <div className={styles.tutorialActions}><Link href="/transactions" className={styles.secondaryButton}>Review Transactions</Link><Link href="/monthly-plan?section=budgets" className={styles.secondaryButton}>Review Budgets</Link></div>
            </section>
          ) : null}

          <section className={styles.monthProgress} aria-labelledby="month-progress-title">
            <div className={styles.progressTop}><div><h2 id="month-progress-title">Month Progress</h2><p>Spending pace compared with the month so far.</p></div><div><span>{data.daysLeft} Days Left</span><Link href="/monthly-plan?section=budgets" className={styles.secondaryButton}>Adjust Budget</Link></div></div>
            <div className={styles.progressTrack}><span className={`${styles.progressFill} ${styles[data.metrics.onTrackStatus]}`} style={{ width: `${Math.min(data.spendPercent, 100)}%` }} /><i style={{ left: `${Math.min(data.pacePercent, 100)}%` }} /></div>
            <div className={styles.progressLabels}><span>$0</span><span>{data.spendPercent}% spent - {data.pacePercent}% through the month</span><span>{currency(data.metrics.safeToSpendTarget)}</span></div>
          </section>

          <PlanTable data={data} />

          <div className={styles.statsGrid}>
            <Link href="/monthly-plan?section=budgets" className={styles.stat}><span>Safe To Spend</span><strong className={data.metrics.safeToSpend < 0 ? styles.negative : data.metrics.safeToSpend < 200 ? "" : styles.positive}>{signedCurrency(data.metrics.safeToSpend)}</strong><small>{data.metrics.safeToSpend < 0 ? "Over budget" : "Remaining This Month"}</small></Link>
            <Link href="/transactions" className={styles.stat}><span>Spent So Far</span><strong>{currency(data.metrics.variableSpend)}</strong><small>Of {currency(data.metrics.safeToSpendTarget)} Plan</small></Link>
            <div className={styles.stat}><span>Net Worth</span><strong className={data.netWorth.netWorth < 0 ? styles.negative : styles.positive}>{signedCurrency(data.netWorth.netWorth)}</strong><small>Tracked Assets Minus Debt</small></div>
          </div>

          <div className={styles.setupGrid}>
            <FeatureTile title="Build Your Budgets" body="Set category budgets and keep spending progress tied to your transactions." href="/monthly-plan?section=budgets" action="Open Budgets" />
            {cashFeature && !cashFeature.hidden ? <FeatureTile title="Forecast Your Future Cash Balance" body={cashFeature.enabled ? "See projected daily cash balances by calendar, list, or graph." : `${cashFeature.requiredPlan} unlocks day-by-day cash balance projections from selected accounts and scheduled activity.`} href={cashFeature.enabled ? "/cash-projections" : "/select-plan"} action={cashFeature.enabled ? "Open Projections" : `Upgrade to ${cashFeature.requiredPlan}`} badge={cashFeature.enabled ? undefined : `Requires ${cashFeature.requiredPlan}`} upgrade={!cashFeature.enabled} /> : null}
            {retirementFeature && !retirementFeature.hidden ? <FeatureTile title="Set Up Retirement Planning" body={retirementFeature.enabled ? "Add or update employer and IRA/Roth contributions for long-range planning." : `${retirementFeature.requiredPlan} unlocks employer plan, IRA/Roth, and long-range retirement scenarios.`} href={retirementFeature.enabled ? "/retirement-plan" : "/select-plan"} action={retirementFeature.enabled ? "Start Planning" : `Upgrade to ${retirementFeature.requiredPlan}`} badge={retirementFeature.enabled ? undefined : `Requires ${retirementFeature.requiredPlan}`} upgrade={!retirementFeature.enabled} /> : null}
          </div>

          {data.dashboardFocus ? (
            <section className={styles.panel} aria-labelledby="focus-title">
              <div className={styles.panelHeader}><div><h2 id="focus-title">Premier Dashboard Focus</h2><p>Built from your latest saved AI Planner guidance.</p></div><Link href="/planner" className={styles.secondaryButton}><Sparkles size={16} aria-hidden="true" />{data.dashboardFocus.items.length ? "Refresh Guidance" : "Generate AI Guidance"}</Link></div>
              {data.dashboardFocus.items.length ? <div className={styles.focusGrid}>{data.dashboardFocus.items.map((item, index) => <article key={`${item.title}-${index}`}><small>{item.type.replaceAll("_", " ")}</small><h3>{item.title}</h3><p>{item.body}</p>{item.action ? <Link href={guidanceTarget(item.action.target)} className={styles.textLink}>{item.action.label}</Link> : null}</article>)}</div> : <div className={styles.empty}><strong>No AI dashboard focus yet</strong><p>{data.dashboardFocus.message}</p></div>}
            </section>
          ) : null}

          <div className={styles.dashboardGrid}>
            <section className={styles.panel} aria-labelledby="guidance-title">
              <div className={styles.panelHeader}><h2 id="guidance-title">This Week&apos;s Guidance</h2>{data.insights.length ? <span className={styles.countBadge}>{data.insights.length} insight{data.insights.length === 1 ? "" : "s"}</span> : null}</div>
              {data.insights.length ? <div className={styles.insightList}>{data.insights.map((insight, index) => <article key={`${insight.type}-${index}`}><span className={`${styles.insightIcon} ${styles[insight.level]}`}>{insight.level === "alert" ? <AlertTriangle size={18} /> : insight.level === "good" ? <TrendingUp size={18} /> : insight.level === "warning" ? <AlertTriangle size={18} /> : <Info size={18} />}</span><div><h3>{insight.title}</h3><p>{insight.body}</p></div></article>)}</div> : <div className={styles.empty}><CircleCheck size={24} aria-hidden="true" /><strong>Nothing Urgent Right Now</strong><p>Your current pace looks steady. Import more transactions for tighter guidance.</p></div>}
            </section>

            <div className={styles.rightStack}>
              <section className={styles.panel} aria-labelledby="categories-title">
                <div className={styles.panelHeader}><h2 id="categories-title">Where The Money Went</h2><Link href="/transactions" className={styles.textLink}>All Transactions</Link></div>
                {data.categoryTotals.length ? <div className={styles.categoryList}>{data.categoryTotals.map((row) => <div className={styles.categoryRow} key={`${row.category}-${row.categoryId ?? "none"}`}><Link href={`/transactions?month=${data.today.slice(0, 7)}&${row.categoryId ? `category_id=${row.categoryId}` : `category_names=${encodeURIComponent(row.category)}`}`}>{row.category}</Link><div><span style={{ width: `${Math.min((row.amount / maxCategory) * 100, 100)}%` }} /></div><strong>{currency(row.amount)}</strong><small>{data.metrics.variableSpend ? Math.round((row.amount / data.metrics.variableSpend) * 100) : 0}%</small></div>)}</div> : <div className={styles.empty}><p>No spending recorded yet.</p></div>}
              </section>

              <section className={styles.panel} aria-labelledby="goals-title">
                <div className={styles.panelHeader}><h2 id="goals-title">Goals</h2><Link href="/goals" className={styles.textLink}>View All</Link></div>
                {data.goals.length ? <div className={styles.goalList}>{data.goals.slice(0, 3).map((goal) => <article key={goal.id}><div className={styles.goalTop}><strong>{goal.name}</strong><span>{Math.round(goal.progress)}%</span>{canEdit ? <button type="button" aria-label={`Delete ${goal.name}`} title={`Delete ${goal.name}`} disabled={deletingGoalId === goal.id} onClick={() => void deleteGoal(goal.id)}><Trash2 size={15} aria-hidden="true" /></button> : null}</div><div className={styles.goalProgress}><span style={{ width: `${Math.min(goal.progress, 100)}%` }} /></div><div className={styles.goalMeta}><span>{currency(goal.currentAmount)} {goal.goalType === "debt" ? "Paid Down" : "Saved"}</span><span>{goal.timeline}</span></div>{goal.targetDate ? <small>Target {dateLabel(goal.targetDate, { month: "2-digit", day: "2-digit", year: "numeric" })}</small> : null}{goal.requiredExtra > 0 ? <small>Extra Needed {currency(goal.requiredExtra)} / Month</small> : goal.requiredMonthly > 0 && goal.goalType === "savings" ? <small>Needed {currency(goal.requiredMonthly)} / Month</small> : null}</article>)}</div> : <div className={styles.empty}><p>No goals yet. Add one to track progress.</p></div>}
              </section>
            </div>
          </div>

          {data.recentTransactions.length ? (
            <section className={styles.panel} aria-labelledby="recent-title">
              <div className={styles.panelHeader}><h2 id="recent-title">Recent Transactions</h2><Link href="/transactions" className={styles.textLink}>View All</Link></div>
              <div className={styles.transactionList}>{data.recentTransactions.map((transaction) => <div className={styles.transactionRow} key={transaction.id}><time dateTime={transaction.postedDate}>{dateLabel(transaction.postedDate, { month: "short", day: "2-digit" })}</time><strong>{transaction.description}</strong><span>{transaction.categoryName ?? "Other"}</span><b className={transaction.amount > 0 ? styles.positive : styles.negative}>{transaction.amount > 0 ? "+" : "-"}{currency(transaction.amount, 2)}</b></div>)}</div>
            </section>
          ) : null}
        </div>
      </div>
    </AuthenticatedShell>
  );
}
