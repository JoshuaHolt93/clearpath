"use client";

import { loanPlanDirectorySchema, type LoanPlanDirectory } from "@clearpath/validation";
import { ChevronDown, Landmark, Plus, RefreshCw } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FormEvent, useCallback, useEffect, useState } from "react";

import { AuthenticatedPageFrame } from "../authenticated-shell";
import styles from "./loan-plans.module.css";

const currency = (value: number, decimals = 0) => new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: decimals, maximumFractionDigits: decimals }).format(value);

async function responseMessage(response: Response, fallback: string) {
  const body = await response.json().catch(() => null) as { message?: string } | null;
  return body?.message || fallback;
}

function canEdit(data: LoanPlanDirectory) {
  return data.session.primaryAccountHolder || data.session.subject.householdRole !== "viewer";
}

export function LoanDirectoryWorkspace() {
  const router = useRouter();
  const [data, setData] = useState<LoanPlanDirectory | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [frequency, setFrequency] = useState("monthly");
  const [weekdayPattern, setWeekdayPattern] = useState("");
  const [category, setCategory] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      const response = await fetch("/api/loan-plans", { cache: "no-store" });
      if (response.status === 403) { router.replace("/select-plan"); return; }
      if (!response.ok) throw new Error(await responseMessage(response, "We could not load mortgage and loan planning."));
      const parsed = loanPlanDirectorySchema.safeParse(await response.json());
      if (!parsed.success) throw new Error("Loan planning data did not match the expected contract.");
      setData(parsed.data);
      setCategory((current) => current || parsed.data.loanCategoryLabelOptions[0] || "Mortgage/Rent");
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "We could not load mortgage and loan planning.");
    }
  }, [router]);

  useEffect(() => { void load(); }, [load]);

  const addLoan = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!data) return;
    setBusy(true);
    setError("");
    const form = new FormData(event.currentTarget);
    const customCategory = String(form.get("customCategory") ?? "").trim();
    const usePattern = Boolean(weekdayPattern);
    const payload = {
      name: String(form.get("name") ?? "").trim(),
      amount: Number(form.get("amount") ?? 0),
      frequency,
      startDate: String(form.get("startDate") ?? ""),
      secondDate: !usePattern && (frequency === "semimonthly" || frequency === "biweekly") ? String(form.get("secondDate") ?? "") || null : null,
      daysOfWeek: usePattern && (frequency === "weekly" || frequency === "biweekly") ? form.getAll("daysOfWeek").map(Number) : [],
      recurringMonthlyWeekNumbers: usePattern && frequency === "semimonthly" ? form.getAll("monthlyWeeks").map(Number) : [],
      recurringMonthlyWeekday: usePattern ? Number(weekdayPattern) : null,
      categoryLabel: category === "Other" ? customCategory : category,
      entryContext: "loan",
      notes: String(form.get("notes") ?? "").trim() || null,
    };
    try {
      const response = await fetch("/api/fixed-expenses", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(payload) });
      if (!response.ok) throw new Error(await responseMessage(response, "We could not add that loan."));
      const result = await response.json() as { itemId: number };
      router.push(`/loan-plans/${result.itemId}`);
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "We could not add that loan.");
      setBusy(false);
    }
  };

  const supportsPattern = ["weekly", "biweekly", "semimonthly"].includes(frequency);
  const showWeekdays = Boolean(weekdayPattern) && ["weekly", "biweekly"].includes(frequency);
  const showMonthWeeks = Boolean(weekdayPattern) && frequency === "semimonthly";
  const showSecondDate = !weekdayPattern && ["biweekly", "semimonthly"].includes(frequency);

  const content = <main className={styles.page}>
    <header className={styles.pageHeader}><div><p className={styles.eyebrow}>Debt Organization</p><h1>Mortgage/Loan Planning</h1><p>A directory of every mortgage or loan currently tracked in your budgets.</p></div></header>
    {error ? <div className={styles.error} role="alert"><span>{error}</span>{!data ? <button type="button" onClick={() => void load()}>Try Again</button> : null}</div> : null}
    {!data && !error ? <div className={styles.loading}><RefreshCw className={styles.spin} size={20} />Loading loan planning...</div> : null}
    {data ? <div className={styles.content}>
      {!canEdit(data) ? <div className={styles.viewerNotice}>You can review tracked balances, payoff plans, and schedules. An owner or editor can add loans or change scenarios.</div> : null}
      <section className={styles.stats} aria-label="Loan planning summary"><article><span>Total Debt Per Month</span><strong>{currency(data.totalDebtMonthly)}</strong><small>Scheduled Payments Plus Selected Extra Principal</small></article><article><span>Current Loan Balances</span><strong>{currency(data.totalDebtBalance)}</strong><small>Current Month Ending Balances</small></article><article><span>Debt-To-Income Ratio</span><strong className={data.debtToIncomeRatio >= .43 ? styles.negative : data.debtToIncomeRatio >= .36 ? styles.neutral : styles.positive}>{Math.round(data.debtToIncomeRatio * 100)}%</strong><small>Common Watch Zone Begins Around 36%</small></article></section>

      <details className={styles.addPanel}>
        <summary><div><h2>Add Loan</h2><p>Create the scheduled payment here, then add amortization details from the loan schedule.</p></div><span><Plus size={15} aria-hidden="true" />Add Loan<ChevronDown size={15} aria-hidden="true" /></span></summary>
        <form className={styles.loanForm} onSubmit={(event) => void addLoan(event)}>
          <div className={styles.formGrid}><label>Loan Name<input name="name" disabled={!canEdit(data) || busy} placeholder="Mortgage, auto loan, student loan..." required /></label><label>Payment Amount<input name="amount" type="number" min="0.01" step="0.01" disabled={!canEdit(data) || busy} required /></label></div>
          <div className={styles.formGrid}><label>Cadence<select value={frequency} disabled={!canEdit(data) || busy} onChange={(event) => { setFrequency(event.target.value); setWeekdayPattern(""); }}>{Object.entries(data.recurringFrequencyOptions).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label><label>First Payment Date<input name="startDate" type="date" defaultValue={data.today} disabled={!canEdit(data) || busy} required /></label></div>
          <div className={styles.formGrid}><label>Loan Category<select value={category} disabled={!canEdit(data) || busy} onChange={(event) => setCategory(event.target.value)}>{data.loanCategoryLabelOptions.map((label) => <option value={label} key={label}>{label}</option>)}<option value="Other">Other Loan Category</option></select></label>{category === "Other" ? <label>Custom Loan Category<input name="customCategory" disabled={!canEdit(data) || busy} placeholder="Personal Loan, HELOC..." required /></label> : null}{supportsPattern ? <label>Weekday Pattern<select value={weekdayPattern} disabled={!canEdit(data) || busy} onChange={(event) => setWeekdayPattern(event.target.value)}><option value="">Calendar Date</option>{Object.entries(data.weekdayOptions).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label> : null}{showSecondDate ? <label>Second Payment Date<input name="secondDate" type="date" disabled={!canEdit(data) || busy} /></label> : null}</div>
          {showWeekdays ? <fieldset className={styles.choiceField}><legend>Days Of Week</legend><div>{Object.entries(data.weekdayOptions).map(([value, label]) => <label key={value}><input type="checkbox" name="daysOfWeek" value={value} defaultChecked={value === weekdayPattern} disabled={!canEdit(data) || busy} /><span>{label.slice(0, 3)}</span></label>)}</div></fieldset> : null}
          {showMonthWeeks ? <fieldset className={styles.choiceField}><legend>Weeks In Month</legend><div>{Object.entries(data.monthlyWeekOptions).map(([value, label]) => <label key={value}><input type="checkbox" name="monthlyWeeks" value={value} disabled={!canEdit(data) || busy} /><span>{label}</span></label>)}</div></fieldset> : null}
          <label>Notes<input name="notes" disabled={!canEdit(data) || busy} placeholder="Optional" /></label>
          <button type="submit" disabled={!canEdit(data) || busy}><Plus size={16} aria-hidden="true" />{busy ? "Adding..." : "Add Loan"}</button>
        </form>
      </details>

      <section className={styles.panel}><header><div><h2>Tracked Loans</h2><p>{data.items.length} mortgage or loan item{data.items.length === 1 ? "" : "s"}</p></div><Link href="/monthly-plan?section=budgets#budget-mortgage-rent">Review Loan Budgets</Link></header>{data.items.length ? <div className={styles.loanList}>{data.items.map((row) => <article key={row.fixedExpenseItemId}><div><div className={styles.loanTitle}><h3>{row.name}</h3><span>{row.loanKind === "mortgage" ? "Mortgage" : "Loan"}</span></div><p>Scheduled {currency(row.monthlyPayment, 2)} / Month{row.selectedExtra ? ` - Extra Principal ${currency(row.selectedExtra, 2)} / Month` : ""}{row.principalBalance ? ` - Current Balance ${currency(row.currentBalance, 2)}${row.collateralValue ? ` - Asset Value ${currency(row.collateralValue, 2)}` : ""} - ${row.selectedScenario.replaceAll("_", " ")} Payoff Plan` : " - Amortization Details Not Set Up Yet"}</p></div><div><strong>{currency(row.totalMonthly, 2)} / Month</strong><Link href={`/loan-plans/${row.fixedExpenseItemId}`}>Open Full Schedule</Link></div></article>)}</div> : <div className={styles.empty}><Landmark size={23} aria-hidden="true" /><strong>No Mortgage Or Loan Items Yet</strong><p>Add a loan above, then open its schedule to compare payoff scenarios and amortization details.</p></div>}</section>
    </div> : null}
  </main>;
  return <AuthenticatedPageFrame session={data?.session}>{content}</AuthenticatedPageFrame>;
}
