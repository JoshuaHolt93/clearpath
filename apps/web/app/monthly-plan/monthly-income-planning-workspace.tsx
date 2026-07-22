"use client";

import { monthlyIncomeEstimate } from "@clearpath/domain";
import { monthlyIncomePlanningViewSchema, type MonthlyIncomePlanningView } from "@clearpath/validation";
import { CalendarClock, Pencil, ReceiptText, Save, Trash2, TriangleAlert, X } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FormEvent, type ReactNode, useCallback, useEffect, useMemo, useState } from "react";

import { AuthenticatedPageFrame } from "../authenticated-shell";
import { refreshLiveBankData } from "@/lib/live-bank-refresh";

import { SavingIndicator } from "../saving-indicator";
import styles from "./monthly-income-planning.module.css";

type IncomeTemplate = MonthlyIncomePlanningView["futureIncomeTemplates"][number];

function currency(value: number, decimals = 0): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency", currency: "USD", minimumFractionDigits: decimals, maximumFractionDigits: decimals,
  }).format(Math.abs(value));
}

function shortDate(value: string): string {
  return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" })
    .format(new Date(`${value}T00:00:00Z`));
}

function splitNumbers(value: string | null): number[] {
  return (value ?? "").split(",").map(Number).filter((item) => Number.isInteger(item));
}

function nullableString(form: FormData, name: string): string | null {
  return String(form.get(name) ?? "").trim() || null;
}

function numberValue(form: FormData, name: string): number {
  return Number(form.get(name) ?? 0);
}

async function responseMessage(response: Response, fallback: string): Promise<string> {
  const body = await response.json().catch(() => null);
  return body && typeof body.message === "string" ? body.message : fallback;
}

function SelectOptions({ options }: { options: Record<string, string> }) {
  return Object.entries(options).map(([value, label]) => <option key={value} value={value}>{label}</option>);
}

function ChoiceGrid({ options, name, selected, abbreviate = true }: {
  options: Record<string, string>; name: string; selected: number[]; abbreviate?: boolean;
}) {
  return (
    <div className={styles.choiceGrid}>
      {Object.entries(options).map(([value, label]) => (
        <label key={value}><input type="checkbox" name={name} value={value} defaultChecked={selected.includes(Number(value))} /><span>{abbreviate ? label.slice(0, 3) : label}</span></label>
      ))}
    </div>
  );
}

function Modal({ title, description, children, onClose, wide = false }: {
  title: string; description: string; children: ReactNode; onClose: () => void; wide?: boolean;
}) {
  return (
    <div className={styles.modalShell} role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className={`${styles.modalPanel} ${wide ? styles.modalWide : ""}`} role="dialog" aria-modal="true" aria-labelledby="income-modal-title">
        <header className={styles.modalHeader}>
          <div><h2 id="income-modal-title">{title}</h2><p>{description}</p></div>
          <button type="button" onClick={onClose} aria-label="Close"><X size={18} /></button>
        </header>
        <div className={styles.modalBody}>{children}</div>
      </section>
    </div>
  );
}

function IncomeScheduleFields({ data, cadence, selectedDays, secondDate, selectedWeeks, selectedWeekday, minimumDate }: {
  data: MonthlyIncomePlanningView; cadence: string; selectedDays: number[]; secondDate: string | null;
  selectedWeeks: number[]; selectedWeekday: number | null; minimumDate?: string;
}) {
  const [monthlyWeekday, setMonthlyWeekday] = useState(selectedWeekday === null ? "" : String(selectedWeekday));
  const [secondPayDate, setSecondPayDate] = useState(secondDate ?? "");
  useEffect(() => {
    if (minimumDate && secondPayDate && secondPayDate < minimumDate) setSecondPayDate("");
  }, [minimumDate, secondPayDate]);
  return (
    <>
      {cadence === "weekly" || cadence === "biweekly" ? (
        <div className={styles.choiceField}><span>Pay Weekdays</span><ChoiceGrid options={data.weekdayOptions} name="payDays" selected={selectedDays} /></div>
      ) : null}
      {cadence === "semimonthly" ? <label>Second Pay Date<input name="secondDate" type="date" min={minimumDate} value={secondPayDate} onChange={(event) => setSecondPayDate(event.target.value)} /></label> : null}
      {cadence === "monthly" || cadence === "semimonthly" ? (
        <div className={styles.scheduleGrid}>
          <label>Weekday Pattern<select name="monthlyWeekday" value={monthlyWeekday} onChange={(event) => setMonthlyWeekday(event.target.value)}><option value="">Calendar Date</option><SelectOptions options={data.weekdayOptions} /></select></label>
          {monthlyWeekday ? <div className={styles.choiceField}><span>Weeks In Month</span><ChoiceGrid options={data.monthlyWeekOptions} name="monthWeeks" selected={selectedWeeks} abbreviate={false} /></div> : null}
        </div>
      ) : null}
    </>
  );
}

function CurrentIncomeForm({ data, canEdit, busy, onSave, onOpenTaxes }: {
  data: MonthlyIncomePlanningView; canEdit: boolean; busy: boolean;
  onSave: (payload: Record<string, unknown>) => Promise<void>; onOpenTaxes: () => void;
}) {
  const profile = data.profile;
  const [basis, setBasis] = useState(profile.incomeBasis ?? "take_home");
  const [incomeType, setIncomeType] = useState(profile.incomeType ?? "salary");
  const [cadence, setCadence] = useState(profile.paycheckCadence ?? profile.incomeFrequency ?? "monthly");
  const [amount, setAmount] = useState(profile.incomeAmountDisplay ?? 0);
  const [hours, setHours] = useState(profile.hourlyHoursPerWeek ?? 40);
  const [additionalAmount, setAdditionalAmount] = useState(profile.additionalIncomeAmount ?? 0);
  const [additionalFrequency, setAdditionalFrequency] = useState(profile.additionalIncomeFrequency ?? "annual");
  const estimate = monthlyIncomeEstimate({
    incomeAmount: amount, incomeType, paycheckCadence: cadence, hourlyHoursPerWeek: hours,
    additionalIncomeAmount: additionalAmount, additionalIncomeFrequency: additionalFrequency,
  });

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    await onSave({
      householdName: nullableString(form, "householdName"), incomeAmount: amount, incomeBasis: basis,
      incomeType, paycheckCadence: cadence, nextPayDate: nullableString(form, "nextPayDate"),
      secondDate: nullableString(form, "secondDate"), recurringDaysOfWeek: form.getAll("payDays").map(Number),
      recurringMonthlyWeekNumbers: form.getAll("monthWeeks").map(Number),
      recurringMonthlyWeekday: nullableString(form, "monthlyWeekday") === null ? null : numberValue(form, "monthlyWeekday"),
      hourlyHoursPerWeek: hours, additionalIncomeAmount: additionalAmount,
      additionalIncomeFrequency: additionalFrequency, taxState: nullableString(form, "taxState"),
      taxFilingStatus: nullableString(form, "taxFilingStatus"), includePayrollTaxes: form.get("includePayrollTaxes") === "on",
      notes: nullableString(form, "notes"), view: "month", section: "baseline",
    });
  };

  const amountLabel = incomeType === "hourly" ? "Hourly Rate" : "Annual Salary";
  const formula = incomeType === "hourly" ? "Hourly Rate X Hours Per Week X 52 / 12" : "Annual Salary / 12";
  return (
    <form className={styles.formStack} onSubmit={submit}>
      <fieldset disabled={!canEdit || busy}>
        <label>Household Name<input name="householdName" defaultValue={profile.householdName ?? ""} /></label>
        <div className={styles.formGridFour}>
          <label>Income Basis<select value={basis} onChange={(event) => setBasis(event.target.value)}><SelectOptions options={data.incomeBasisOptions} /></select><small>Gross is before taxes.</small></label>
          <label>Income Type<select value={incomeType} onChange={(event) => setIncomeType(event.target.value)}>{Object.entries(data.incomeTypeOptions).filter(([value]) => value !== "bonus").map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
          <label>Paycheck Or Bonus Cadence<select value={cadence} onChange={(event) => setCadence(event.target.value)}><SelectOptions options={data.paycheckCadenceOptions} /></select><small>Used for pay-period planning.</small></label>
          <label>Next Pay Date<input name="nextPayDate" type="date" defaultValue={profile.nextPayDate ?? data.today} /></label>
        </div>
        <IncomeScheduleFields data={data} cadence={cadence} selectedDays={splitNumbers(profile.paycheckDaysOfWeek)} secondDate={profile.paycheckSecondDate} selectedWeeks={splitNumbers(profile.paycheckMonthlyWeekNumbers)} selectedWeekday={profile.paycheckMonthlyWeekday} />
        <div className={styles.formGridFour}>
          <label>{amountLabel}<input name="incomeAmount" type="number" min="0" step="0.01" value={amount} onChange={(event) => setAmount(Number(event.target.value))} /><small>{incomeType === "hourly" ? "Enter hourly rate." : "Enter annual salary."}</small></label>
          {incomeType === "hourly" ? <label>Hours Per Week<input name="hourlyHoursPerWeek" type="number" min="0" step="0.1" value={hours} onChange={(event) => setHours(Number(event.target.value))} /></label> : null}
          <label>{basis === "gross" ? "Estimated Monthly Gross Income" : "Estimated Monthly Take-Home Income"}<input value={estimate.toFixed(2)} disabled /><small>{formula}{additionalAmount > 0 ? " + Bonus/Other Income" : ""}.</small></label>
          <label>Bonus Or Other Income Amount<input name="additionalIncomeAmount" type="number" min="0" step="0.01" value={additionalAmount} onChange={(event) => setAdditionalAmount(Number(event.target.value))} /></label>
          <label>Bonus Cadence<select name="additionalIncomeFrequency" value={additionalFrequency} onChange={(event) => setAdditionalFrequency(event.target.value)}><SelectOptions options={data.recurringFrequencyOptions} /></select></label>
        </div>
        {basis === "gross" ? (
          <div className={styles.formGrid}>
            <label>Tax Filing Status<select name="taxFilingStatus" defaultValue={profile.taxFilingStatus ?? "married_joint"}><SelectOptions options={data.taxFilingStatusOptions} /></select></label>
            <label>Tax State<select name="taxState" defaultValue={profile.taxState ?? ""}><option value="">No state selected</option><SelectOptions options={data.stateOptions} /></select></label>
            <label className={styles.toggleLabel}><input name="includePayrollTaxes" type="checkbox" defaultChecked={profile.includePayrollTaxes ?? false} />Include Social Security And Medicare Taxes</label>
          </div>
        ) : null}
        <label>Planning Notes<input name="notes" defaultValue={profile.notes ?? ""} placeholder="School, travel, bonus timing, seasonal costs..." /></label>
      </fieldset>
      {canEdit ? <div className={styles.formActions}><button type="submit" disabled={busy}><Save size={16} />Save Income Plan</button><button type="button" className={styles.secondaryButton} onClick={onOpenTaxes}><ReceiptText size={16} />Tax Planning Module</button></div> : <p className={styles.viewerNote}>Shared viewers can review this income plan but cannot change it.</p>}
    </form>
  );
}

function FutureIncomeForm({ data, item, busy, onSave, onDelete }: {
  data: MonthlyIncomePlanningView; item?: IncomeTemplate; busy: boolean;
  onSave: (payload: Record<string, unknown>) => Promise<void>; onDelete?: () => Promise<void>;
}) {
  const profile = data.profile;
  const [basis, setBasis] = useState(item?.incomeBasis ?? profile.incomeBasis ?? "take_home");
  const [incomeType, setIncomeType] = useState(item?.incomeType ?? profile.incomeType ?? "salary");
  const [cadence, setCadence] = useState(item?.paycheckCadence ?? item?.frequency ?? profile.paycheckCadence ?? "monthly");
  const [amount, setAmount] = useState(item?.amount ?? profile.incomeAmountDisplay ?? 0);
  const [hours, setHours] = useState(item?.hourlyHoursPerWeek ?? profile.hourlyHoursPerWeek ?? 40);
  const [additionalAmount, setAdditionalAmount] = useState(item?.additionalIncomeAmount ?? profile.additionalIncomeAmount ?? 0);
  const [additionalFrequency, setAdditionalFrequency] = useState(item?.additionalIncomeFrequency ?? profile.additionalIncomeFrequency ?? "annual");
  const initialStartDate = item?.startDate ?? data.today;
  const initialFirstPayDate = item?.incomeNextPayDate ?? item?.startDate ?? profile.nextPayDate ?? data.today;
  const [startDate, setStartDate] = useState(initialStartDate);
  const [firstPayDate, setFirstPayDate] = useState(initialFirstPayDate < initialStartDate ? initialStartDate : initialFirstPayDate);
  const estimate = monthlyIncomeEstimate({
    incomeAmount: amount, incomeType, paycheckCadence: cadence, hourlyHoursPerWeek: hours,
    additionalIncomeAmount: additionalAmount, additionalIncomeFrequency: additionalFrequency,
  });
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    await onSave({
      name: nullableString(form, "name"), amount, itemType: "income", frequency: cadence, startDate,
      secondDate: nullableString(form, "secondDate"), recurringDaysOfWeek: form.getAll("payDays").map(Number),
      recurringMonthlyWeekNumbers: form.getAll("monthWeeks").map(Number),
      recurringMonthlyWeekday: nullableString(form, "monthlyWeekday") === null ? null : numberValue(form, "monthlyWeekday"),
      categoryLabel: "Income", notes: nullableString(form, "notes"), incomeAdjustment: true,
      incomeReplacement: form.get("incomeReplacement") !== "no", incomeBasis: basis, incomeType,
      paycheckCadence: cadence, incomeNextPayDate: nullableString(form, "incomeNextPayDate"), incomeAmount: amount,
      hourlyHoursPerWeek: hours, additionalIncomeAmount: additionalAmount, additionalIncomeFrequency: additionalFrequency,
      taxState: nullableString(form, "taxState"), taxFilingStatus: nullableString(form, "taxFilingStatus"),
      includePayrollTaxes: form.get("includePayrollTaxes") === "on",
    });
  };
  const amountLabel = incomeType === "hourly" ? "Hourly Rate" : incomeType === "bonus" ? "Bonus/Other Amount" : "Annual Salary";
  return (
    <form className={styles.formStack} onSubmit={submit}>
      <div className={styles.formGrid}>
        <label>Adjustment Name<input name="name" defaultValue={item?.name ?? ""} placeholder="Raise, bonus, side contract..." required /></label>
        <label>Adjustment Type<select name="incomeReplacement" defaultValue={item?.incomeReplacement === false ? "no" : "yes"}><option value="yes">Replace current income from the start date</option><option value="no">Add as another income stream</option></select></label>
      </div>
      <div className={styles.formGridFour}>
        <label>Income Basis<select value={basis} onChange={(event) => setBasis(event.target.value)}><SelectOptions options={data.incomeBasisOptions} /></select></label>
        <label>Income Type<select value={incomeType} onChange={(event) => setIncomeType(event.target.value)}><SelectOptions options={data.incomeTypeOptions} /></select></label>
        <label>Paycheck Or Bonus Cadence<select value={cadence} onChange={(event) => setCadence(event.target.value)}><SelectOptions options={data.paycheckCadenceOptions} /></select></label>
        <label>Adjustment Start Date<input name="startDate" type="date" value={startDate} onChange={(event) => { const nextStart = event.target.value; setStartDate(nextStart); if (firstPayDate < nextStart) setFirstPayDate(nextStart); }} required /></label>
        <label>First Pay Date<input name="incomeNextPayDate" type="date" min={startDate} value={firstPayDate} onChange={(event) => setFirstPayDate(event.target.value)} required /></label>
        <label>{amountLabel}<input name="incomeAmount" type="number" min="0.01" step="0.01" value={amount} onChange={(event) => setAmount(Number(event.target.value))} required /></label>
        <label>{basis === "gross" ? "Estimated Monthly Gross Income" : "Estimated Monthly Take-Home Income"}<input value={estimate.toFixed(2)} disabled /></label>
      </div>
      <IncomeScheduleFields data={data} cadence={cadence} selectedDays={splitNumbers(item?.daysOfWeek ?? null)} secondDate={item?.secondDate ?? null} selectedWeeks={splitNumbers(item?.monthlyWeekNumbers ?? null)} selectedWeekday={item?.monthlyWeekday ?? null} minimumDate={startDate} />
      {incomeType === "hourly" ? <label>Hours Per Week<input name="hourlyHoursPerWeek" type="number" min="0" step="0.1" value={hours} onChange={(event) => setHours(Number(event.target.value))} /></label> : null}
      <div className={styles.formGrid}>
        <label>Bonus Or Other Income Amount<input name="additionalIncomeAmount" type="number" min="0" step="0.01" value={additionalAmount} onChange={(event) => setAdditionalAmount(Number(event.target.value))} /></label>
        <label>Bonus Cadence<select value={additionalFrequency} onChange={(event) => setAdditionalFrequency(event.target.value)}><SelectOptions options={data.recurringFrequencyOptions} /></select></label>
      </div>
      {basis === "gross" ? <div className={styles.formGrid}><label>Tax Filing Status<select name="taxFilingStatus" defaultValue={item?.taxFilingStatus ?? profile.taxFilingStatus ?? "married_joint"}><SelectOptions options={data.taxFilingStatusOptions} /></select></label><label>Tax State<select name="taxState" defaultValue={item?.taxState ?? profile.taxState ?? ""}><option value="">No state selected</option><SelectOptions options={data.stateOptions} /></select></label><label className={styles.toggleLabel}><input name="includePayrollTaxes" type="checkbox" defaultChecked={item?.includePayrollTaxes ?? profile.includePayrollTaxes ?? false} />Include Social Security And Medicare Taxes</label></div> : null}
      <label>Notes<input name="notes" defaultValue={item?.notes ?? ""} placeholder="Optional context" /></label>
      <div className={styles.formActions}><button type="submit" disabled={busy}><Save size={16} />{item ? "Save Adjustment" : "Add Income Adjustment"}</button>{onDelete ? <button type="button" className={styles.dangerButton} disabled={busy} onClick={() => void onDelete()}><Trash2 size={16} />Delete</button> : null}</div>
    </form>
  );
}

function TaxPlanningModule({ data, busy, onSave, onClose }: {
  data: MonthlyIncomePlanningView; busy: boolean; onSave: (payload: Record<string, unknown>) => Promise<void>; onClose: () => void;
}) {
  const tax = data.taxEstimate;
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    await onSave({
      baselineScope: "core", taxAdditionalLabel: nullableString(form, "taxAdditionalLabel"),
      taxAdditionalType: nullableString(form, "taxAdditionalType"), taxAdditionalMonthlyAmount: numberValue(form, "taxAdditionalMonthlyAmount"),
      taxAdditionalRate: numberValue(form, "taxAdditionalRate"), view: "month", section: "baseline",
    });
  };
  return (
    <Modal title="Tax Planning Module" description="Review how taxes are estimated and which tables are used in Budgets." onClose={onClose} wide>
      <div className={styles.taxStats}><div><span>Monthly Tax Estimate</span><strong>{currency(tax.monthlyTotal)}</strong><small>Included in expected cash flow.</small></div><div><span>Annual Tax Estimate</span><strong>{currency(tax.annualTotal)}</strong><small>Based on current baseline settings.</small></div><div><span>Taxable Income</span><strong>{currency(tax.taxableIncome)}</strong><small>Gross income minus standard deduction.</small></div></div>
      <div className={styles.taxColumns}>
        <section><h3>Tax Breakdown</h3><dl><div><dt>Federal Income Tax</dt><dd>{currency(tax.federalIncomeTax / 12)} / Month</dd></div><div><dt>State Income Tax</dt><dd>{currency(tax.stateIncomeTax / 12)} / Month</dd></div><div><dt>Social Security Tax</dt><dd>{currency(tax.socialSecurityTax / 12)} / Month</dd></div><div><dt>Medicare Tax</dt><dd>{currency((tax.medicareTax + tax.additionalMedicareTax) / 12)} / Month</dd></div><div><dt>{tax.additionalTaxLabel}</dt><dd>{currency(tax.additionalTaxMonthly)} / Month{tax.additionalTaxType === "percent" ? ` (${tax.additionalTaxRate}%)` : ""}</dd></div></dl></section>
        <section><h3>Current Tax Settings</h3><dl><div><dt>Filing Status</dt><dd>{data.taxFilingStatusOptions[tax.filingStatus] ?? tax.filingStatus}</dd></div><div><dt>Tax State</dt><dd>{tax.state ? data.stateOptions[tax.state] ?? tax.state : "Not Selected"}</dd></div><div><dt>Calculated Gross Annual Income</dt><dd>{currency(tax.annualGrossIncome)}</dd></div><div><dt>State Method</dt><dd>{tax.stateMethod}</dd></div></dl><p className={styles.callout}>Gross annual income is calculated from Income Planning and paycheck cadence.</p></section>
      </div>
      <section className={styles.taxSection}><div className={styles.sectionTitle}><div><h3>Additional Tax Worksheet</h3><p>County, city, local, or other paycheck taxes not covered by the default tables.</p></div></div><form className={styles.formStack} onSubmit={submit}><div className={styles.formGridFour}><label>Tax Label<input name="taxAdditionalLabel" defaultValue={data.profile.taxAdditionalLabel ?? "Additional Local Tax"} /></label><label>Tax Method<select name="taxAdditionalType" defaultValue={data.profile.taxAdditionalType ?? "amount"}><option value="amount">Monthly Amount</option><option value="percent">Percentage Of Gross Income</option></select></label><label>Additional Monthly Tax<input name="taxAdditionalMonthlyAmount" type="number" min="0" step="0.01" defaultValue={data.profile.taxAdditionalMonthlyAmount ?? 0} /></label><label>Additional Tax Rate<input name="taxAdditionalRate" type="number" min="0" step="0.001" defaultValue={data.profile.taxAdditionalRate ?? 0} /></label></div>{!data.taxesEnabled ? <p className={styles.callout}>Additional taxes are saved here, but join plan math only when Income Basis is Gross Income.</p> : null}<button type="submit" disabled={busy}><Save size={16} />Save Tax Worksheet</button></form></section>
      <section className={styles.taxSection}><div className={styles.sectionTitle}><h3>Federal 2026 Income Tax Table Used</h3><a href="https://www.irs.gov/publications/p505#en_US_2026_publink1000194749" target="_blank" rel="noopener noreferrer">IRS Source</a></div><div className={styles.tableWrap}><table><thead><tr><th>Over</th><th>But Not Over</th><th>Base Tax</th><th>Plus Rate</th><th>Of Amount Over</th></tr></thead><tbody>{tax.federalBrackets.map((row, index) => <tr key={index}><td>{currency(row[0] ?? 0)}</td><td>{row[1] === null ? "No Limit" : currency(row[1] ?? 0)}</td><td>{currency(row[2] ?? 0, 2)}</td><td>{((row[3] ?? 0) * 100).toFixed(0)}%</td><td>{currency(row[0] ?? 0)}</td></tr>)}</tbody></table></div></section>
      <div className={styles.taxColumns}>
        <section><h3>Payroll Tax Table Used</h3><dl><div><dt>Social Security</dt><dd>6.2% Up To $184,500</dd></div><div><dt>Medicare</dt><dd>1.45% No Wage Cap</dd></div><div><dt>Additional Medicare</dt><dd>0.9% Above Filing Threshold</dd></div></dl></section>
        <section><div className={styles.sectionTitle}><h3>State Tax Table Used</h3>{tax.stateSourceUrl ? <a href={tax.stateSourceUrl} target="_blank" rel="noopener noreferrer">State Source</a> : null}</div><dl><div><dt>Selected State</dt><dd>{tax.state ? data.stateOptions[tax.state] ?? tax.state : "Not Selected"}</dd></div><div><dt>Method</dt><dd>{tax.stateMethod}</dd></div><div><dt>State Taxable Income</dt><dd>{currency(tax.stateTaxableIncome)}</dd></div><div><dt>State Deduction</dt><dd>{currency(tax.stateStandardDeduction)}</dd></div><div><dt>State Exemption</dt><dd>{currency(tax.statePersonalExemption)}</dd></div><div><dt>State Credit</dt><dd>{currency(tax.stateCredit)}</dd></div><div><dt>Calculated State Rate</dt><dd>{tax.stateRate.toFixed(2)}%</dd></div></dl><p className={styles.callout}>{tax.stateNote}</p></section>
      </div>
    </Modal>
  );
}

export function MonthlyIncomePlanningWorkspace() {
  const router = useRouter();
  const [data, setData] = useState<MonthlyIncomePlanningView | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [refreshWarning, setRefreshWarning] = useState<string | null>(null);
  const [editing, setEditing] = useState<IncomeTemplate | null>(null);
  const [taxOpen, setTaxOpen] = useState(false);
  const [createFormVersion, setCreateFormVersion] = useState(0);

  const loadPlan = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const response = await fetch("/api/monthly-plan?section=baseline", { cache: "no-store" });
      if (response.status === 401) { router.replace("/login?next=%2Fmonthly-plan%3Fsection%3Dbaseline"); return; }
      if (response.status === 409) { router.replace("/onboarding"); return; }
      if (response.status === 403) { router.replace("/monthly-plan?section=tools"); return; }
      if (!response.ok) throw new Error(await responseMessage(response, "We could not load Income Planning."));
      const parsed = monthlyIncomePlanningViewSchema.safeParse(await response.json());
      if (!parsed.success) throw new Error("ClearPath returned invalid income planning details.");
      setData(parsed.data);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "We could not load Income Planning.");
    } finally { setLoading(false); }
  }, [router]);

  useEffect(() => { void loadPlan(); }, [loadPlan]);

  // Refresh live bank data after the page renders. Awaiting this before the
  // first fetch left the loading screen up for the whole Plaid sync, with no
  // timeout if it stalled.
  useEffect(() => {
    let cancelled = false;
    void refreshLiveBankData().then((result) => {
      if (cancelled) return;
      setRefreshWarning(result.warning);
      if (result.synced) void loadPlan();
    });
    return () => { cancelled = true; };
  }, [loadPlan]);

  const canEdit = data ? data.session.primaryAccountHolder || data.session.subject.householdRole === "editor" : false;
  const orderedTemplates = useMemo(() => data?.futureIncomeTemplates ?? [], [data]);

  const runMutation = async (key: string, path: string, options: RequestInit, success: string): Promise<boolean> => {
    setBusy(key); setError(null); setNotice(null);
    try {
      const response = await fetch(path, options);
      if (!response.ok) throw new Error(await responseMessage(response, "We could not save that income planning change."));
      setNotice(success); setEditing(null); await loadPlan(); return true;
    } catch (mutationError) {
      setError(mutationError instanceof Error ? mutationError.message : "We could not save that income planning change."); return false;
    } finally { setBusy(null); }
  };
  const saveBaseline = (payload: Record<string, unknown>) => runMutation("baseline", "/api/monthly-plan/baseline", { method: "PATCH", headers: { "content-type": "application/json" }, body: JSON.stringify(payload) }, "Income plan updated.").then(() => undefined);
  const saveTax = async (payload: Record<string, unknown>) => { const saved = await runMutation("tax", "/api/monthly-plan/baseline", { method: "PATCH", headers: { "content-type": "application/json" }, body: JSON.stringify(payload) }, "Tax worksheet updated."); if (saved) setTaxOpen(false); };
  const saveFuture = async (payload: Record<string, unknown>) => {
    const editedItem = editing;
    const saved = await runMutation(editedItem ? `edit-${editedItem.id}` : "create", editedItem ? `/api/recurring-templates/${editedItem.id}` : "/api/recurring-templates", { method: editedItem ? "PATCH" : "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(payload) }, editedItem ? "Income adjustment updated." : "Income adjustment added.");
    if (saved && !editedItem) setCreateFormVersion((version) => version + 1);
  };
  const deleteFuture = async () => {
    if (!editing || !window.confirm("Delete this future income adjustment?")) return;
    await runMutation(`delete-${editing.id}`, `/api/recurring-templates/${editing.id}`, { method: "DELETE", headers: { "content-type": "application/json" }, body: JSON.stringify({ confirm: true }) }, "Income adjustment removed.");
  };

  if (loading && !data) return <AuthenticatedPageFrame activePlanSection="baseline"><div className={styles.loadingPage}><span className="logo-mark">C</span><strong>Loading Income Planning...</strong></div></AuthenticatedPageFrame>;
  if (!data) return <div className={styles.loadingPage}><div className={styles.loadError}><TriangleAlert size={24} /><p>{error ?? "We could not load Income Planning."}</p><button type="button" onClick={() => void loadPlan()}>Try Again</button></div></div>;

  return (
    <AuthenticatedPageFrame session={data.session} activePlanSection="baseline">
      <div className={styles.page}>
        <header className={styles.pageHeader}><div><h1>Income Planning</h1><p>Plan future raises, job changes, bonuses, or side income while keeping setup income as the baseline.</p></div><span><CalendarClock size={16} />Future-Aware</span></header>
        <main className={styles.content}>
          {refreshWarning ? <div className={styles.warning}><TriangleAlert size={18} />{refreshWarning}</div> : null}
          {error ? <div className={styles.error} role="alert"><TriangleAlert size={18} />{error}</div> : null}
          {notice ? <div className={styles.notice} role="status">{notice}</div> : null}
          {busy ? <SavingIndicator /> : null}
          {!canEdit ? <div className={styles.viewerBand}>You have view-only household access. Income settings and adjustments are read-only.</div> : null}
          <section className={styles.intro}><strong>Use Income Planning for income changes that have not happened yet.</strong><p>Your setup income is the current baseline. Future changes feed forecasts before they reach transactions.</p></section>
          <details className={styles.currentPanel} id="baseline">
            <summary><div><h2>Adjust Current Income</h2><p>Open when setup income, tax basis, or paycheck timing needs correction.</p></div><span>Review Or Edit</span></summary>
            <div className={styles.panelBody}><CurrentIncomeForm data={data} canEdit={canEdit} busy={busy === "baseline"} onSave={saveBaseline} onOpenTaxes={() => setTaxOpen(true)} /></div>
          </details>
          <section className={styles.futurePanel} id="future-income">
            <header className={styles.sectionTitle}><div><h2>Future Income Planning</h2><p>Schedule known changes before they happen. They feed forecasts once dates enter the horizon.</p></div><span>{orderedTemplates.length} Scheduled</span></header>
            {canEdit ? <div className={styles.panelBody}><FutureIncomeForm key={createFormVersion} data={data} busy={busy === "create"} onSave={saveFuture} /></div> : null}
            <div className={styles.templateList}>
              {orderedTemplates.map((template) => <div className={styles.templateRow} key={template.id}><div><strong>{template.name}</strong><span>{template.incomeReplacement ? "Replacement income" : "Additional income stream"} starting {shortDate(template.startDate)}{template.notes ? ` - ${template.notes}` : ""}</span></div><div><strong>{currency(template.amount, 2)}</strong>{canEdit ? <button type="button" onClick={() => setEditing(template)}><Pencil size={14} />Edit</button> : null}</div></div>)}
              {!orderedTemplates.length ? <div className={styles.empty}>No future income adjustments yet. Add one only when a known change should affect planning.</div> : null}
            </div>
          </section>
          <nav className={styles.footerLinks} aria-label="Monthly plan sections"><Link href="/monthly-plan?section=tools">Quick Planning</Link><Link href="/monthly-plan?section=forecast">3-Month Forecast</Link><Link href="/monthly-plan?section=budgets">Budgets</Link></nav>
        </main>
      </div>
      {editing ? <Modal title="Edit Future Income" description={editing.name} onClose={() => setEditing(null)} wide><FutureIncomeForm data={data} item={editing} busy={Boolean(busy)} onSave={saveFuture} onDelete={deleteFuture} /></Modal> : null}
      {taxOpen ? <TaxPlanningModule data={data} busy={busy === "tax"} onSave={saveTax} onClose={() => setTaxOpen(false)} /> : null}
    </AuthenticatedPageFrame>
  );
}
