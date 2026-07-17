"use client";

import {
  onboardingIncomePlanRequestSchema,
  onboardingStatusSchema,
  plaidLinkTokenResultSchema,
  type OnboardingStatus,
} from "@clearpath/validation";
import Link from "next/link";
import { useRouter } from "next/navigation";
import Script from "next/script";
import { type FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import styles from "./onboarding.module.css";

type SetupStep = OnboardingStatus["activeStep"];
type PlaidMetadata = Record<string, unknown>;
type PlaidError = { error_code?: string; error_message?: string } | null;

declare global {
  interface Window {
    Plaid?: {
      create(config: {
        token: string;
        onSuccess(publicToken: string, metadata: PlaidMetadata): void;
        onExit(error: PlaidError, metadata: PlaidMetadata): void;
      }): { open(): void };
    };
  }
}

type IncomeForm = {
  incomeBasis: "take_home" | "gross";
  incomeType: "salary" | "hourly";
  paycheckCadence: "annual" | "monthly" | "semimonthly" | "biweekly" | "weekly" | "irregular";
  nextPayDate: string;
  secondDate: string;
  weekdays: number[];
  monthlyWeekNumbers: number[];
  monthlyWeekday: string;
  incomeAmount: string;
  hourlyHoursPerWeek: string;
  additionalIncomeAmount: string;
  additionalIncomeFrequency: "weekly" | "biweekly" | "semimonthly" | "monthly" | "quarterly" | "annual";
  taxFilingStatus: string;
  taxState: string;
  includePayrollTaxes: boolean;
  notes: string;
};

const EMPTY_FORM: IncomeForm = {
  incomeBasis: "take_home",
  incomeType: "salary",
  paycheckCadence: "monthly",
  nextPayDate: "",
  secondDate: "",
  weekdays: [],
  monthlyWeekNumbers: [],
  monthlyWeekday: "",
  incomeAmount: "",
  hourlyHoursPerWeek: "40",
  additionalIncomeAmount: "",
  additionalIncomeFrequency: "annual",
  taxFilingStatus: "married_joint",
  taxState: "",
  includePayrollTaxes: true,
  notes: "",
};

function numericList(value: string | null): number[] {
  return (value ?? "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean)
    .map((item) => Number(item))
    .filter((item) => Number.isInteger(item));
}

function formFromStatus(status: OnboardingStatus): IncomeForm {
  const profile = status.profile;
  const incomeType = profile.incomeType === "hourly" ? "hourly" : "salary";
  const cadence = ["annual", "monthly", "semimonthly", "biweekly", "weekly", "irregular"].includes(profile.paycheckCadence ?? "")
    ? (profile.paycheckCadence as IncomeForm["paycheckCadence"])
    : "monthly";
  const additionalFrequency = ["weekly", "biweekly", "semimonthly", "monthly", "quarterly", "annual"].includes(
    profile.additionalIncomeFrequency ?? "",
  )
    ? (profile.additionalIncomeFrequency as IncomeForm["additionalIncomeFrequency"])
    : "annual";
  return {
    ...EMPTY_FORM,
    incomeBasis: profile.incomeBasis === "gross" ? "gross" : "take_home",
    incomeType,
    paycheckCadence: cadence,
    nextPayDate: profile.nextPayDate ?? status.today,
    secondDate: profile.paycheckSecondDate ?? "",
    weekdays: numericList(profile.paycheckDaysOfWeek),
    monthlyWeekNumbers: numericList(profile.paycheckMonthlyWeekNumbers),
    monthlyWeekday: profile.paycheckMonthlyWeekday === null ? "" : String(profile.paycheckMonthlyWeekday),
    incomeAmount: profile.incomeAmountDisplay ? String(profile.incomeAmountDisplay) : "",
    hourlyHoursPerWeek: String(profile.hourlyHoursPerWeek ?? 40),
    additionalIncomeAmount: profile.additionalIncomeAmount ? String(profile.additionalIncomeAmount) : "",
    additionalIncomeFrequency: additionalFrequency,
    taxFilingStatus: profile.taxFilingStatus ?? "married_joint",
    taxState: profile.taxState ?? "",
    includePayrollTaxes: profile.includePayrollTaxes ?? true,
    notes: profile.notes ?? "",
  };
}

function parseNumber(value: string): number {
  const parsed = Number(value.replace(/[$,]/g, ""));
  return Number.isFinite(parsed) ? parsed : 0;
}

function monthlyize(value: number, frequency: IncomeForm["additionalIncomeFrequency"]): number {
  if (frequency === "annual") return value / 12;
  if (frequency === "quarterly") return (value * 4) / 12;
  if (frequency === "semimonthly") return (value * 24) / 12;
  if (frequency === "biweekly") return (value * 26) / 12;
  if (frequency === "weekly") return (value * 52) / 12;
  return value;
}

function formatCurrency(value: number): string {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(Math.abs(value));
}

async function responseMessage(response: Response, fallback: string): Promise<string> {
  const body = await response.json().catch(() => null);
  return body && typeof body.message === "string" ? body.message : fallback;
}

export function OnboardingWorkspace({ initialStep }: { initialStep: SetupStep }) {
  const router = useRouter();
  const [status, setStatus] = useState<OnboardingStatus | null>(null);
  const [form, setForm] = useState<IncomeForm>(EMPTY_FORM);
  const [categorySelections, setCategorySelections] = useState<Record<number, number>>({});
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [savingTransactionId, setSavingTransactionId] = useState<number | null>(null);
  const [plaidLoaded, setPlaidLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const applyStatus = useCallback((next: OnboardingStatus) => {
    setStatus(next);
    setForm(formFromStatus(next));
    setCategorySelections(
      Object.fromEntries(
        next.transactions
          .filter((transaction) => transaction.categoryId !== null)
          .map((transaction) => [transaction.id, transaction.categoryId as number]),
      ),
    );
    setError(null);
  }, []);

  const loadStep = useCallback(async (step: SetupStep) => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`/api/onboarding?step=${step}`, { cache: "no-store" });
      if (!response.ok) {
        throw new Error(await responseMessage(response, "We could not load your setup progress."));
      }
      const parsed = onboardingStatusSchema.safeParse(await response.json());
      if (!parsed.success) {
        throw new Error("ClearPath returned invalid setup details.");
      }
      applyStatus(parsed.data);
      window.history.replaceState(null, "", `/onboarding?step=${parsed.data.activeStep}`);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "We could not load your setup progress.");
    } finally {
      setLoading(false);
    }
  }, [applyStatus]);

  useEffect(() => {
    void loadStep(initialStep);
  }, [initialStep, loadStep]);

  const estimatedMonthlyIncome = useMemo(() => {
    const base = parseNumber(form.incomeAmount);
    const baseMonthly = form.incomeType === "hourly"
      ? (base * (parseNumber(form.hourlyHoursPerWeek) || 40) * 52) / 12
      : base / 12;
    return baseMonthly + monthlyize(parseNumber(form.additionalIncomeAmount), form.additionalIncomeFrequency);
  }, [form]);

  const moveToStep = async (step: SetupStep) => {
    if (busy || loading) return;
    await loadStep(step);
  };

  const reportPlaidEvent = async (eventName: string, plaidError: PlaidError, metadata: PlaidMetadata) => {
    await fetch("/api/onboarding/plaid/link-events", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ event_name: eventName, error: plaidError, metadata }),
    }).catch(() => undefined);
  };

  const connectBank = async () => {
    if (!window.Plaid) {
      setError("Plaid is still loading. Try again in a moment.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const response = await fetch("/api/onboarding/plaid/link-token", { method: "POST" });
      if (!response.ok) {
        throw new Error(await responseMessage(response, "Plaid could not start a secure bank connection."));
      }
      const parsed = plaidLinkTokenResultSchema.safeParse(await response.json());
      if (!parsed.success) throw new Error("ClearPath returned invalid Plaid setup details.");
      const handler = window.Plaid.create({
        token: parsed.data.linkToken,
        onSuccess: async (publicToken, metadata) => {
          const exchange = await fetch("/api/onboarding/plaid/exchange-public-token", {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({
              public_token: publicToken,
              metadata,
              consent_token: parsed.data.consentToken,
            }),
          });
          if (!exchange.ok) {
            setError(await responseMessage(exchange, "Plaid connected, but ClearPath could not save it."));
            setBusy(false);
            return;
          }
          setBusy(false);
          await loadStep("income");
        },
        onExit: (plaidError, metadata) => {
          void reportPlaidEvent("EXIT", plaidError, metadata);
          setError(
            plaidError?.error_code
              ? `Bank connection did not finish (${plaidError.error_code}). ${plaidError.error_message ?? "Try again."}`
              : "Bank connection was closed before it finished.",
          );
          setBusy(false);
        },
      });
      handler.open();
    } catch (connectError) {
      setError(connectError instanceof Error ? connectError.message : "Plaid could not start a secure bank connection.");
      setBusy(false);
    }
  };

  const submitIncome = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const payload = onboardingIncomePlanRequestSchema.safeParse({
      income_amount: parseNumber(form.incomeAmount),
      income_basis: form.incomeBasis,
      income_type: form.incomeType,
      paycheck_cadence: form.paycheckCadence,
      next_pay_date: form.nextPayDate || null,
      second_date: form.secondDate || null,
      recurring_days_of_week: form.weekdays,
      recurring_monthly_week_numbers: form.monthlyWeekNumbers,
      recurring_monthly_weekday: form.monthlyWeekday === "" ? null : Number(form.monthlyWeekday),
      hourly_hours_per_week: parseNumber(form.hourlyHoursPerWeek) || 40,
      fixed_expenses: 0,
      variable_expenses: 0,
      additional_income_amount: parseNumber(form.additionalIncomeAmount),
      additional_income_frequency: form.additionalIncomeFrequency,
      planned_savings_contribution: 0,
      planned_debt_payment: 0,
      target_investment_contribution: 0,
      tax_filing_status: form.taxFilingStatus,
      tax_state: form.taxState || null,
      include_payroll_taxes: form.includePayrollTaxes,
      notes: form.notes,
    });
    if (!payload.success) {
      const issue = payload.error.issues[0];
      const field = String(issue?.path.at(-1) ?? "income details").replaceAll("_", " ");
      setError(issue ? `Check ${field}. ${issue.message}` : "Check your income details.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const response = await fetch("/api/onboarding", {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(payload.data),
      });
      if (!response.ok) throw new Error(await responseMessage(response, "We could not save your income plan."));
      const parsed = onboardingStatusSchema.safeParse(await response.json());
      if (!parsed.success) throw new Error("ClearPath returned invalid setup details.");
      applyStatus(parsed.data);
      window.history.replaceState(null, "", "/onboarding?step=transactions");
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "We could not save your income plan.");
    } finally {
      setBusy(false);
    }
  };

  const saveCategory = async (transactionId: number) => {
    const categoryId = categorySelections[transactionId];
    if (!categoryId) {
      setError("Choose a category.");
      return;
    }
    setSavingTransactionId(transactionId);
    setError(null);
    try {
      const response = await fetch(`/api/onboarding/transactions/${transactionId}/category`, {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ category_id: categoryId }),
      });
      if (!response.ok) throw new Error(await responseMessage(response, "We could not update that transaction."));
      setStatus((current) => current ? {
        ...current,
        transactions: current.transactions.map((transaction) => (
          transaction.id === transactionId ? { ...transaction, categoryId } : transaction
        )),
      } : current);
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "We could not update that transaction.");
    } finally {
      setSavingTransactionId(null);
    }
  };

  const finishSetup = async () => {
    setBusy(true);
    setError(null);
    try {
      const response = await fetch("/api/onboarding", { method: "POST" });
      if (!response.ok) throw new Error(await responseMessage(response, "We could not finish setup."));
      const parsed = onboardingStatusSchema.safeParse(await response.json());
      if (!parsed.success) throw new Error("ClearPath returned invalid setup details.");
      applyStatus(parsed.data);
      if (parsed.data.nextPath) router.push(parsed.data.nextPath);
    } catch (finishError) {
      setError(finishError instanceof Error ? finishError.message : "We could not finish setup.");
    } finally {
      setBusy(false);
    }
  };

  const toggleNumber = (field: "weekdays" | "monthlyWeekNumbers", value: number) => {
    setForm((current) => ({
      ...current,
      [field]: current[field].includes(value)
        ? current[field].filter((item) => item !== value)
        : [...current[field], value].sort((left, right) => left - right),
    }));
  };

  const expenseCategories = status?.categories.filter((category) => category.kind === "expense") ?? [];
  const usesMonthlyPattern = ["monthly", "semimonthly"].includes(form.paycheckCadence) && form.monthlyWeekday !== "";

  return (
    <div className={styles.page}>
      <Script src="https://cdn.plaid.com/link/v2/stable/link-initialize.js" onLoad={() => setPlaidLoaded(true)} />
      <header className={styles.header}>
        <Link href="/" className={styles.brand} aria-label="ClearPath Finance home">
          <span className="logo-mark">C</span>
          <span><strong>ClearPath</strong><small>Finance</small></span>
        </Link>
        <span className={styles.setupLabel}>Account Setup</span>
      </header>

      <main className={styles.main} aria-busy={loading}>
        <div className={styles.heading}>
          <p className={styles.eyebrow}>Your financial baseline</p>
          <h1>Set Up ClearPath</h1>
          <p>Connect an account, define income, and review the first budget categories.</p>
        </div>

        <nav className={styles.steps} aria-label="Setup progress">
          <button type="button" className={status?.activeStep === "connect" ? styles.activeStep : ""} onClick={() => void moveToStep("connect")}>
            <span>1</span> Connect
          </button>
          <button type="button" className={status?.activeStep === "income" ? styles.activeStep : ""} disabled={!status?.hasBank} onClick={() => void moveToStep("income")}>
            <span>2</span> Income
          </button>
          <button type="button" className={status?.activeStep === "transactions" ? styles.activeStep : ""} disabled={!status?.incomeReady || !status.hasBank} onClick={() => void moveToStep("transactions")}>
            <span>3</span> Review
          </button>
        </nav>

        {error ? <div className={styles.error} role="alert">{error}</div> : null}
        {loading ? <div className={styles.loading} role="status">Loading setup...</div> : null}

        {!loading && status?.activeStep === "connect" ? (
          <section className={styles.workspace} aria-labelledby="connect-title">
            <div className={styles.sectionHeader}>
              <div><h2 id="connect-title">Connect Your First Account</h2><p>Start with live transactions so budgets reflect real spending.</p></div>
              <span className={`${styles.badge} ${status.hasBank ? styles.successBadge : ""}`}>{status.hasBank ? "Connected" : status.plaidStatus.ready ? "Ready" : "Unavailable"}</span>
            </div>
            {status.plaidItems.length ? (
              <>
                <div className={styles.institutionList}>
                  {status.plaidItems.map((item) => (
                    <div className={styles.institutionRow} key={item.id}>
                      <div><strong>{item.institutionName ?? "Connected Institution"}</strong><span>{item.status.replaceAll("_", " ")}</span></div>
                      {item.lastSyncedAt ? <time dateTime={item.lastSyncedAt}>{new Date(item.lastSyncedAt).toLocaleDateString()}</time> : <span>Sync pending</span>}
                    </div>
                  ))}
                </div>
                <div className={styles.actions}><button type="button" className={styles.primaryButton} onClick={() => void moveToStep("income")}>Continue To Income</button></div>
              </>
            ) : status.plaidStatus.ready ? (
              <div className={styles.connectAction}>
                <div><strong>Secure bank connection</strong><p>Choose the institution and accounts used for household planning.</p></div>
                <button type="button" className={styles.primaryButton} onClick={() => void connectBank()} disabled={busy || !plaidLoaded}>{busy ? "Opening Plaid..." : "Connect Bank Account"}</button>
              </div>
            ) : (
              <div className={styles.notice}><strong>Plaid Is Not Fully Configured Yet</strong><p>SDK {status.plaidStatus.sdkInstalled ? "ready" : "missing"}; credentials {status.plaidStatus.hasCredentials ? "ready" : "missing"}; encryption key {status.plaidStatus.hasEncryptionKey ? "ready" : "missing"}.</p></div>
            )}
            {!status.hasBank && status.plaidStatus.environment === "sandbox" ? (
              <dl className={styles.sandbox}><div><dt>Institution</dt><dd>First Platypus Bank</dd></div><div><dt>Username</dt><dd>user_good</dd></div><div><dt>Password</dt><dd>pass_good</dd></div><div><dt>MFA Code</dt><dd>1234</dd></div></dl>
            ) : null}
          </section>
        ) : null}

        {!loading && status?.activeStep === "income" ? (
          <section className={styles.workspace} aria-labelledby="income-title">
            <div className={styles.sectionHeader}>
              <div><h2 id="income-title">Set Your Income</h2><p>Define the monthly planning baseline and paycheck timing.</p></div>
              <span className={`${styles.badge} ${status.incomeReady ? styles.successBadge : ""}`}>{status.incomeReady ? "Saved" : "Required"}</span>
            </div>
            <form className={styles.form} onSubmit={submitIncome}>
              <div className={styles.formGridFour}>
                <label><span>Income Basis</span><select value={form.incomeBasis} onChange={(event) => setForm({ ...form, incomeBasis: event.target.value as IncomeForm["incomeBasis"] })}>{Object.entries(status.incomeBasisOptions).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
                <label><span>Income Type</span><select value={form.incomeType} onChange={(event) => setForm({ ...form, incomeType: event.target.value as IncomeForm["incomeType"] })}>{Object.entries(status.incomeTypeOptions).filter(([value]) => value !== "bonus").map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
                <label><span>Paycheck Cadence</span><select value={form.paycheckCadence} onChange={(event) => setForm({ ...form, paycheckCadence: event.target.value as IncomeForm["paycheckCadence"] })}>{Object.entries(status.paycheckCadenceOptions).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
                <label><span>Next Pay Date</span><input type="date" value={form.nextPayDate} onChange={(event) => setForm({ ...form, nextPayDate: event.target.value })} /></label>
              </div>

              {form.paycheckCadence === "weekly" || form.paycheckCadence === "biweekly" ? (
                <fieldset className={styles.choiceField}><legend>Pay Weekdays</legend><div className={styles.choiceGrid}>{Object.entries(status.weekdayOptions).map(([value, label]) => { const number = Number(value); return <label key={value}><input type="checkbox" checked={form.weekdays.includes(number)} onChange={() => toggleNumber("weekdays", number)} /><span>{label.slice(0, 3)}</span></label>; })}</div></fieldset>
              ) : null}

              {form.paycheckCadence === "monthly" || form.paycheckCadence === "semimonthly" ? (
                <div className={styles.formGrid}>
                  <label><span>Weekday Pattern</span><select value={form.monthlyWeekday} onChange={(event) => setForm({ ...form, monthlyWeekday: event.target.value })}><option value="">Calendar Date</option>{Object.entries(status.weekdayOptions).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
                  {form.paycheckCadence === "semimonthly" && !usesMonthlyPattern ? <label><span>Second Pay Date</span><input type="date" value={form.secondDate} onChange={(event) => setForm({ ...form, secondDate: event.target.value })} /></label> : null}
                </div>
              ) : null}

              {usesMonthlyPattern ? (
                <fieldset className={styles.choiceField}><legend>Weeks In Month</legend><div className={styles.choiceGrid}>{Object.entries(status.monthlyWeekOptions).map(([value, label]) => { const number = Number(value); return <label key={value}><input type="checkbox" checked={form.monthlyWeekNumbers.includes(number)} onChange={() => toggleNumber("monthlyWeekNumbers", number)} /><span>{label}</span></label>; })}</div></fieldset>
              ) : null}

              <div className={styles.formGridThree}>
                <label><span>{form.incomeType === "hourly" ? "Hourly Rate" : "Annual Salary"}</span><div className={styles.moneyInput}><b>$</b><input aria-label={form.incomeType === "hourly" ? "Hourly Rate" : "Annual Salary"} inputMode="decimal" value={form.incomeAmount} onChange={(event) => setForm({ ...form, incomeAmount: event.target.value })} required /></div></label>
                {form.incomeType === "hourly" ? <label><span>Hours Per Week</span><input inputMode="decimal" value={form.hourlyHoursPerWeek} onChange={(event) => setForm({ ...form, hourlyHoursPerWeek: event.target.value })} /></label> : null}
                <label><span>{form.incomeBasis === "gross" ? "Estimated Monthly Gross Income" : "Estimated Monthly Take-Home Income"}</span><input value={formatCurrency(estimatedMonthlyIncome)} readOnly /></label>
              </div>

              <div className={styles.formGrid}>
                <label><span>Bonus Or Other Income Amount</span><div className={styles.moneyInput}><b>$</b><input inputMode="decimal" value={form.additionalIncomeAmount} onChange={(event) => setForm({ ...form, additionalIncomeAmount: event.target.value })} /></div></label>
                <label><span>Bonus Cadence</span><select value={form.additionalIncomeFrequency} onChange={(event) => setForm({ ...form, additionalIncomeFrequency: event.target.value as IncomeForm["additionalIncomeFrequency"] })}>{Object.entries(status.recurringFrequencyOptions).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
              </div>

              {form.incomeBasis === "gross" ? (
                <><div className={styles.formGrid}><label><span>Tax Filing Status</span><select value={form.taxFilingStatus} onChange={(event) => setForm({ ...form, taxFilingStatus: event.target.value })}>{Object.entries(status.taxFilingStatusOptions).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><label><span>Tax State</span><select value={form.taxState} onChange={(event) => setForm({ ...form, taxState: event.target.value })}>{Object.entries(status.stateOptions).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label></div><label className={styles.toggle}><input type="checkbox" checked={form.includePayrollTaxes} onChange={(event) => setForm({ ...form, includePayrollTaxes: event.target.checked })} /><span>Include Social Security And Medicare Taxes</span></label></>
              ) : null}

              <label><span>Notes</span><input value={form.notes} onChange={(event) => setForm({ ...form, notes: event.target.value })} placeholder="Optional context about your income or financial season" /></label>
              <div className={styles.actions}><button type="submit" className={styles.primaryButton} disabled={busy}>{busy ? "Saving..." : "Save Income And Continue"}</button></div>
            </form>
          </section>
        ) : null}

        {!loading && status?.activeStep === "transactions" ? (
          <section className={styles.workspace} aria-labelledby="review-title">
            <div className={styles.sectionHeader}>
              <div><h2 id="review-title">Review A Few Transactions</h2><p>Check the first category examples before ClearPath seeds the budget view.</p></div>
              <span className={styles.badge}>{status.transactions.length} To Review</span>
            </div>
            {status.message ? <div className={styles.successNotice} role="status">{status.message}</div> : null}
            {status.autoCategorizedCount ? <div className={styles.notice}><strong>ClearPath categorized {status.autoCategorizedCount} transaction{status.autoCategorizedCount === 1 ? "" : "s"} automatically.</strong></div> : null}
            {status.transactions.length ? (
              <div className={styles.transactionList}>
                {status.transactions.map((transaction) => (
                  <div className={styles.transactionRow} key={transaction.id}>
                    <div className={styles.transactionIdentity}><strong>{transaction.displayMerchant}</strong><span>{transaction.postedDate} - {transaction.accountName ?? transaction.sourceName ?? "Imported transaction"}</span></div>
                    <span className={styles.amount}>{formatCurrency(transaction.amount)}</span>
                    <div className={styles.categoryAction}>
                      <label className={styles.srOnly} htmlFor={`category-${transaction.id}`}>Category for {transaction.displayMerchant}</label>
                      <select id={`category-${transaction.id}`} value={categorySelections[transaction.id] ?? ""} onChange={(event) => setCategorySelections({ ...categorySelections, [transaction.id]: Number(event.target.value) })}><option value="">Choose category</option>{expenseCategories.map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}</select>
                      <button type="button" className={styles.secondaryButton} disabled={savingTransactionId === transaction.id} onClick={() => void saveCategory(transaction.id)}>{savingTransactionId === transaction.id ? "Saving..." : "Save"}</button>
                    </div>
                  </div>
                ))}
              </div>
            ) : <div className={styles.empty}><strong>No Training Transactions Yet</strong><p>Finish setup now and continue cleanup when synced transactions arrive.</p></div>}
            <div className={styles.actions}><button type="button" className={styles.primaryButton} disabled={busy} onClick={() => void finishSetup()}>{busy ? "Finishing..." : "Finish Setup"}</button></div>
          </section>
        ) : null}
      </main>

      <footer className={styles.footer}><Link href="/terms">Terms</Link><Link href="/privacy">Privacy</Link></footer>
    </div>
  );
}
