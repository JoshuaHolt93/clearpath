"use client";

import { monthlyQuickPlanningViewSchema, type MonthlyQuickPlanningView } from "@clearpath/validation";
import {
  ArrowDownUp,
  CalendarClock,
  ChevronRight,
  Landmark,
  Pencil,
  Plus,
  Save,
  Trash2,
  TriangleAlert,
  X,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FormEvent, type ReactNode, useCallback, useEffect, useMemo, useState } from "react";

import { AuthenticatedPageFrame } from "../authenticated-shell";
import { refreshLiveBankData } from "@/lib/live-bank-refresh";

import { SavingIndicator } from "../saving-indicator";
import styles from "./monthly-quick-planning.module.css";

export type MonthlyQuickPlanningQuery = { quickSort: string };
type FixedItem = MonthlyQuickPlanningView["fixedItems"][number];
type VariableItem = MonthlyQuickPlanningView["variableItems"][number];
type ForecastItem = MonthlyQuickPlanningView["forecastItems"][number];
type RecurringItem = MonthlyQuickPlanningView["recurringTemplates"][number];
type Editor =
  | { kind: "fixed"; item?: FixedItem }
  | { kind: "variable"; item?: VariableItem }
  | { kind: "forecast"; item?: ForecastItem }
  | { kind: "recurring"; item: RecurringItem };

const frequencyFallback: Record<string, string> = {
  once: "Once", weekly: "Weekly", biweekly: "Every Two Weeks", semimonthly: "Twice Per Month",
  monthly: "Monthly", quarterly: "Quarterly", annual: "Annual",
};

function currency(value: number, decimals = 0): string {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: decimals, maximumFractionDigits: decimals }).format(Math.abs(value));
}

function signedCurrency(value: number, decimals = 0): string {
  return `${value < 0 ? "-" : value > 0 ? "+" : ""}${currency(value, decimals)}`;
}

function shortDate(value: string): string {
  return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", timeZone: "UTC" }).format(new Date(`${value}T00:00:00Z`));
}

function routeForQuery(query: MonthlyQuickPlanningQuery): string {
  const params = new URLSearchParams({ section: "tools" });
  if (query.quickSort !== "amount_desc") params.set("quick_sort", query.quickSort);
  return `/monthly-plan?${params.toString()}`;
}

function apiRouteForQuery(query: MonthlyQuickPlanningQuery): string {
  return `/api${routeForQuery(query)}`;
}

async function responseMessage(response: Response, fallback: string): Promise<string> {
  const payload = await response.json().catch(() => null);
  return payload && typeof payload.message === "string" ? payload.message : fallback;
}

function featureEnabled(data: MonthlyQuickPlanningView, feature: string): boolean {
  return data.session.featureAccess.some((row) => row.feature === feature && row.enabled && !row.hidden);
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

function Modal({ title, description, children, onClose }: { title: string; description: string; children: ReactNode; onClose: () => void }) {
  return (
    <div className={styles.modalShell} role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className={styles.modalPanel} role="dialog" aria-modal="true" aria-labelledby="planning-modal-title">
        <header className={styles.modalHeader}>
          <div><h2 id="planning-modal-title">{title}</h2><p>{description}</p></div>
          <button type="button" className={styles.iconButton} onClick={onClose} aria-label="Close"><X size={18} /></button>
        </header>
        <div className={styles.modalBody}>{children}</div>
      </section>
    </div>
  );
}

function SelectOptions({ options }: { options: Record<string, string> }) {
  return Object.entries(Object.keys(options).length ? options : frequencyFallback).map(([value, label]) => <option key={value} value={value}>{label}</option>);
}

function WeekdayChoices({ options, name, selected, abbreviate = true }: { options: Record<string, string>; name: string; selected: number[]; abbreviate?: boolean }) {
  return (
    <div className={styles.choiceGrid}>
      {Object.entries(options).map(([value, label]) => (
        <label key={value}><input type="checkbox" name={name} value={value} defaultChecked={selected.includes(Number(value))} /><span>{abbreviate ? label.slice(0, 3) : label}</span></label>
      ))}
    </div>
  );
}

function CategoryField({ data, defaultValue }: { data: MonthlyQuickPlanningView; defaultValue?: string | null }) {
  return (
    <label>Category Label
      <input name="categoryLabel" list="planning-category-options" defaultValue={defaultValue ?? ""} placeholder="Choose category" />
      <datalist id="planning-category-options">{data.categoryLabelOptions.map((option) => <option key={option} value={option} />)}</datalist>
    </label>
  );
}

function FixedExpenseForm({ data, item, busy, onSave, onDelete }: {
  data: MonthlyQuickPlanningView; item?: FixedItem; busy: boolean;
  onSave: (payload: Record<string, unknown>) => Promise<void>; onDelete?: () => Promise<void>;
}) {
  const [frequency, setFrequency] = useState(item?.frequency ?? "monthly");
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    await onSave({
      name: nullableString(form, "name"), amount: numberValue(form, "amount"), frequency,
      startDate: nullableString(form, "startDate"), secondDate: nullableString(form, "secondDate"),
      daysOfWeek: form.getAll("daysOfWeek").map(Number), recurringMonthlyWeekNumbers: [],
      recurringMonthlyWeekday: null, categoryLabel: nullableString(form, "categoryLabel"),
      entryContext: item?.isLoan ? "loan" : null, notes: nullableString(form, "notes"),
    });
  };
  return (
    <form className={styles.formStack} onSubmit={submit}>
      <div className={styles.formGrid}>
        <label>Expense Name<input name="name" defaultValue={item?.name ?? ""} placeholder="Rent, insurance, daycare..." required /></label>
        <label>Amount For Selected Cadence<input name="amount" type="number" inputMode="decimal" min="0.01" step="0.01" defaultValue={item?.amount ?? ""} required /></label>
        <label>Cadence<select name="frequency" value={frequency} onChange={(event) => setFrequency(event.target.value)}><SelectOptions options={data.recurringFrequencyOptions} /></select></label>
        <label>Date<input name="startDate" type="date" defaultValue={item?.startDate ?? data.today} required /></label>
      </div>
      {frequency === "weekly" || frequency === "biweekly" ? <div className={styles.choiceField}><span>Days Of Week</span><WeekdayChoices options={data.weekdayOptions} name="daysOfWeek" selected={splitNumbers(item?.daysOfWeek ?? null)} /></div> : null}
      {frequency === "semimonthly" ? <label>Second Date<input name="secondDate" type="date" defaultValue={item?.secondDate ?? ""} /></label> : null}
      <div className={styles.formGrid}><CategoryField data={data} defaultValue={item?.categoryLabel} /><label>Notes<input name="notes" defaultValue={item?.notes ?? ""} placeholder="Optional" /></label></div>
      <div className={styles.formActions}>
        <button type="submit" disabled={busy}><Save size={16} />{item ? "Save Fixed Expense" : "Add Fixed Expense"}</button>
        {onDelete ? <button type="button" className={styles.dangerButton} disabled={busy} onClick={() => void onDelete()}><Trash2 size={16} />Delete</button> : null}
      </div>
    </form>
  );
}

function VariableExpenseForm({ data, item, busy, onSave, onDelete }: {
  data: MonthlyQuickPlanningView; item?: VariableItem; busy: boolean;
  onSave: (payload: Record<string, unknown>) => Promise<void>; onDelete?: () => Promise<void>;
}) {
  const [frequency, setFrequency] = useState(item?.frequency ?? "monthly");
  const [specific, setSpecific] = useState(item?.useSpecificDate ?? false);
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    await onSave({
      name: nullableString(form, "name"), amount: numberValue(form, "amount"), frequency,
      useSpecificDate: specific, specificDate: specific ? nullableString(form, "specificDate") : null,
      daysOfWeek: specific ? form.getAll("daysOfWeek").map(Number) : [],
      categoryLabel: nullableString(form, "categoryLabel"), notes: nullableString(form, "notes"),
    });
  };
  return (
    <form className={styles.formStack} onSubmit={submit}>
      <div className={styles.formGrid}>
        <label>Expense Bucket<input name="name" defaultValue={item?.name ?? ""} placeholder="Groceries, gas, school lunches..." required /></label>
        <label>Amount For Selected Cadence<input name="amount" type="number" inputMode="decimal" min="0.01" step="0.01" defaultValue={item?.amount ?? ""} required /></label>
        <label>Cadence<select value={frequency} onChange={(event) => setFrequency(event.target.value)}><SelectOptions options={data.recurringFrequencyOptions} /></select></label>
        <label className={styles.toggleLabel}><input type="checkbox" checked={specific} onChange={(event) => setSpecific(event.target.checked)} />Plan On Specific Timing</label>
      </div>
      {specific && (frequency === "weekly" || frequency === "biweekly") ? <div className={styles.choiceField}><span>Days Of Week</span><WeekdayChoices options={data.weekdayOptions} name="daysOfWeek" selected={splitNumbers(item?.daysOfWeek ?? null)} /></div> : null}
      {specific && frequency !== "weekly" && frequency !== "biweekly" ? <label>Date<input name="specificDate" type="date" defaultValue={item?.specificDate ?? data.today} /></label> : null}
      <div className={styles.formGrid}><CategoryField data={data} defaultValue={item?.categoryLabel} /><label>Notes<input name="notes" defaultValue={item?.notes ?? ""} placeholder="Optional context" /></label></div>
      <div className={styles.formActions}>
        <button type="submit" disabled={busy}><Save size={16} />{item ? "Save Flexible Budget" : "Add Flexible Budget"}</button>
        {onDelete ? <button type="button" className={styles.dangerButton} disabled={busy} onClick={() => void onDelete()}><Trash2 size={16} />Delete</button> : null}
      </div>
    </form>
  );
}

function ForecastItemForm({ data, item, busy, onSave, onDelete }: {
  data: MonthlyQuickPlanningView; item?: ForecastItem; busy: boolean;
  onSave: (payload: Record<string, unknown>) => Promise<void>; onDelete?: () => Promise<void>;
}) {
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    await onSave({ itemDate: nullableString(form, "itemDate"), description: nullableString(form, "description"), amount: numberValue(form, "amount"), itemType: "expense", categoryLabel: nullableString(form, "categoryLabel"), notes: nullableString(form, "notes") });
  };
  return (
    <form className={styles.formStack} onSubmit={submit}>
      <div className={styles.formGrid}>
        <label>Date<input name="itemDate" type="date" defaultValue={item?.itemDate ?? data.today} required /></label>
        <label>Description<input name="description" defaultValue={item?.description ?? ""} placeholder="Trip deposit, repair, annual bill..." required /></label>
        <label>Amount<input name="amount" type="number" inputMode="decimal" min="0.01" step="0.01" defaultValue={item?.amount ?? ""} required /></label>
        <CategoryField data={data} defaultValue={item?.categoryLabel} />
      </div>
      <label>Notes<input name="notes" defaultValue={item?.notes ?? ""} placeholder="Optional context" /></label>
      <div className={styles.formActions}>
        <button type="submit" disabled={busy}><Save size={16} />{item ? "Save One-Time Expense" : "Add One-Time Expense"}</button>
        {onDelete ? <button type="button" className={styles.dangerButton} disabled={busy} onClick={() => void onDelete()}><Trash2 size={16} />Delete</button> : null}
      </div>
    </form>
  );
}

function RecurringTemplateForm({ data, item, busy, onSave, onDelete }: {
  data: MonthlyQuickPlanningView; item: RecurringItem; busy: boolean;
  onSave: (payload: Record<string, unknown>) => Promise<void>; onDelete: () => Promise<void>;
}) {
  const [frequency, setFrequency] = useState(item.frequency);
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    await onSave({
      name: nullableString(form, "name"), amount: numberValue(form, "amount"), itemType: item.itemType,
      frequency, startDate: nullableString(form, "startDate"), secondDate: nullableString(form, "secondDate"),
      recurringDaysOfWeek: form.getAll("daysOfWeek").map(Number),
      recurringMonthlyWeekNumbers: form.getAll("monthlyWeeks").map(Number),
      recurringMonthlyWeekday: nullableString(form, "monthlyWeekday") === null ? null : numberValue(form, "monthlyWeekday"),
      categoryLabel: nullableString(form, "categoryLabel"), notes: nullableString(form, "notes"), incomeAdjustment: false,
    });
  };
  return (
    <form className={styles.formStack} onSubmit={submit}>
      <div className={styles.formGrid}>
        <label>Description<input name="name" defaultValue={item.name} required /></label>
        <label>Amount For Selected Cadence<input name="amount" type="number" inputMode="decimal" min="0.01" step="0.01" defaultValue={item.amount} required /></label>
        <label>Cadence<select value={frequency} onChange={(event) => setFrequency(event.target.value)}><SelectOptions options={data.recurringFrequencyOptions} /></select></label>
        <label>Start Date<input name="startDate" type="date" defaultValue={item.startDate} required /></label>
      </div>
      {frequency === "weekly" || frequency === "biweekly" ? <div className={styles.choiceField}><span>Days Of Week</span><WeekdayChoices options={data.weekdayOptions} name="daysOfWeek" selected={splitNumbers(item.daysOfWeek)} /></div> : null}
      {frequency === "semimonthly" ? <label>Second Date<input name="secondDate" type="date" defaultValue={item.secondDate ?? ""} /></label> : null}
      {frequency === "monthly" || frequency === "semimonthly" ? (
        <div className={styles.formGrid}>
          <label>Weekday Pattern<select name="monthlyWeekday" defaultValue={item.monthlyWeekday ?? ""}><option value="">Calendar Date</option>{Object.entries(data.weekdayOptions).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
          <div className={styles.choiceField}><span>Weeks In Month</span><WeekdayChoices options={data.monthlyWeekOptions} name="monthlyWeeks" selected={splitNumbers(item.monthlyWeekNumbers)} abbreviate={false} /></div>
        </div>
      ) : null}
      <div className={styles.formGrid}><CategoryField data={data} defaultValue={item.categoryLabel} /><label>Notes<input name="notes" defaultValue={item.notes ?? ""} /></label></div>
      <div className={styles.formActions}><button type="submit" disabled={busy}><Save size={16} />Save Recurring Item</button><button type="button" className={styles.dangerButton} disabled={busy} onClick={() => void onDelete()}><Trash2 size={16} />Delete</button></div>
    </form>
  );
}

function BaselineForm({ data, canEdit, busy, onSave }: { data: MonthlyQuickPlanningView; canEdit: boolean; busy: boolean; onSave: (payload: Record<string, unknown>) => Promise<void> }) {
  const profile = data.profile;
  const [cadence, setCadence] = useState(profile.paycheckCadence ?? profile.incomeFrequency ?? "monthly");
  const [incomeBasis, setIncomeBasis] = useState(profile.incomeBasis ?? "take_home");
  const [incomeType, setIncomeType] = useState(profile.incomeType ?? "salary");
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    await onSave({
      baselineScope: "core", householdName: nullableString(form, "householdName"),
      incomeAmount: numberValue(form, "incomeAmount"), incomeBasis, incomeType, paycheckCadence: cadence,
      nextPayDate: nullableString(form, "nextPayDate"), secondDate: nullableString(form, "secondDate"),
      recurringDaysOfWeek: form.getAll("payDays").map(Number), recurringMonthlyWeekNumbers: form.getAll("monthWeeks").map(Number),
      recurringMonthlyWeekday: nullableString(form, "monthlyWeekday") === null ? null : numberValue(form, "monthlyWeekday"),
      hourlyHoursPerWeek: numberValue(form, "hourlyHoursPerWeek"), additionalIncomeAmount: numberValue(form, "additionalIncomeAmount"),
      additionalIncomeFrequency: nullableString(form, "additionalIncomeFrequency"), taxState: nullableString(form, "taxState"),
      taxFilingStatus: nullableString(form, "taxFilingStatus"), includePayrollTaxes: form.get("includePayrollTaxes") === "on",
      notes: nullableString(form, "notes"), view: "month", section: "tools",
    });
  };
  return (
    <form className={styles.formStack} onSubmit={submit}>
      <fieldset disabled={!canEdit || busy}>
        <label>Household Name<input name="householdName" defaultValue={profile.householdName ?? ""} /></label>
        <div className={styles.formGridFour}>
          <label>Income Basis<select value={incomeBasis} onChange={(event) => setIncomeBasis(event.target.value)}><SelectOptions options={data.incomeBasisOptions} /></select></label>
          <label>Income Type<select value={incomeType} onChange={(event) => setIncomeType(event.target.value)}>{Object.entries(data.incomeTypeOptions).filter(([key]) => key !== "bonus").map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
          <label>Paycheck Cadence<select value={cadence} onChange={(event) => setCadence(event.target.value)}><SelectOptions options={data.paycheckCadenceOptions} /></select></label>
          <label>Next Pay Date<input name="nextPayDate" type="date" defaultValue={profile.nextPayDate ?? data.today} /></label>
        </div>
        {(cadence === "weekly" || cadence === "biweekly") ? <div className={styles.choiceField}><span>Pay Weekdays</span><WeekdayChoices options={data.weekdayOptions} name="payDays" selected={splitNumbers(profile.paycheckDaysOfWeek)} /></div> : null}
        {cadence === "semimonthly" ? <label>Second Pay Date<input name="secondDate" type="date" defaultValue={profile.paycheckSecondDate ?? ""} /></label> : null}
        {(cadence === "monthly" || cadence === "semimonthly") ? (
          <div className={styles.formGrid}>
            <label>Weekday Pattern<select name="monthlyWeekday" defaultValue={profile.paycheckMonthlyWeekday ?? ""}><option value="">Calendar Date</option>{Object.entries(data.weekdayOptions).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
            <div className={styles.choiceField}><span>Weeks In Month</span><WeekdayChoices options={data.monthlyWeekOptions} name="monthWeeks" selected={splitNumbers(profile.paycheckMonthlyWeekNumbers)} abbreviate={false} /></div>
          </div>
        ) : null}
        <div className={styles.formGridFour}>
          <label>{incomeType === "hourly" ? "Hourly Rate" : "Annual Salary"}<input name="incomeAmount" type="number" min="0" step="0.01" defaultValue={profile.incomeAmountDisplay ?? 0} /></label>
          {incomeType === "hourly" ? <label>Hours Per Week<input name="hourlyHoursPerWeek" type="number" min="0" step="0.1" defaultValue={profile.hourlyHoursPerWeek ?? 40} /></label> : null}
          <label>Estimated Monthly Income<input value={data.planIncome.toFixed(2)} disabled /></label>
          <label>Other Income<input name="additionalIncomeAmount" type="number" min="0" step="0.01" defaultValue={profile.additionalIncomeAmount ?? 0} /></label>
          <label>Other Income Cadence<select name="additionalIncomeFrequency" defaultValue={profile.additionalIncomeFrequency ?? "annual"}><SelectOptions options={data.recurringFrequencyOptions} /></select></label>
        </div>
        {incomeBasis === "gross" ? (
          <div className={styles.formGrid}>
            <label>Tax Filing Status<select name="taxFilingStatus" defaultValue={profile.taxFilingStatus ?? "married_joint"}><SelectOptions options={data.taxFilingStatusOptions} /></select></label>
            <label>Tax State<select name="taxState" defaultValue={profile.taxState ?? ""}><option value="">No state selected</option><SelectOptions options={data.stateOptions} /></select></label>
            <label className={styles.toggleLabel}><input name="includePayrollTaxes" type="checkbox" defaultChecked={profile.includePayrollTaxes ?? false} />Include Social Security And Medicare Taxes</label>
          </div>
        ) : null}
        <label>Planning Notes<input name="notes" defaultValue={profile.notes ?? ""} placeholder="School, travel, bonus timing, seasonal costs..." /></label>
      </fieldset>
      {canEdit ? <button type="submit" disabled={busy}><Save size={16} />Save Baseline</button> : <p className={styles.viewerNote}>Shared viewers can review this baseline but cannot change it.</p>}
    </form>
  );
}

export function MonthlyQuickPlanningWorkspace({ query }: { query: MonthlyQuickPlanningQuery }) {
  const router = useRouter();
  const [data, setData] = useState<MonthlyQuickPlanningView | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [refreshWarning, setRefreshWarning] = useState<string | null>(null);
  const [editor, setEditor] = useState<Editor | null>(null);

  const loadPlan = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const response = await fetch(apiRouteForQuery(query), { cache: "no-store" });
      if (response.status === 401) { router.replace(`/login?next=${encodeURIComponent(routeForQuery(query))}`); return; }
      if (response.status === 409) { router.replace("/onboarding"); return; }
      if (!response.ok) throw new Error(await responseMessage(response, "We could not load Quick Planning."));
      const parsed = monthlyQuickPlanningViewSchema.safeParse(await response.json());
      if (!parsed.success) throw new Error("ClearPath returned invalid planning details.");
      setData(parsed.data);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "We could not load Quick Planning.");
    } finally { setLoading(false); }
  }, [query, router]);

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
  const projection = data?.quickCashProjection ?? null;
  const forecastExpenses = useMemo(() => data?.forecastItems.filter((item) => item.itemType === "expense") ?? [], [data]);

  const runMutation = async (key: string, path: string, options: RequestInit, success: string): Promise<boolean> => {
    setBusy(key); setError(null); setNotice(null);
    try {
      const response = await fetch(path, options);
      if (!response.ok) throw new Error(await responseMessage(response, "We could not save that planning change."));
      setNotice(success); setEditor(null); await loadPlan(); return true;
    } catch (mutationError) {
      setError(mutationError instanceof Error ? mutationError.message : "We could not save that planning change."); return false;
    } finally { setBusy(null); }
  };

  const saveEditor = async (payload: Record<string, unknown>) => {
    if (!editor) return;
    const existingId = editor.item?.id;
    const base = editor.kind === "fixed" ? "/api/fixed-expenses" : editor.kind === "variable" ? "/api/variable-expenses" : editor.kind === "forecast" ? "/api/forecast-items" : "/api/recurring-templates";
    const path = existingId ? `${base}/${existingId}` : base;
    const label = editor.kind === "variable" ? "Flexible budget" : editor.kind === "forecast" ? "One-time expense" : editor.kind === "recurring" ? "Recurring item" : "Fixed expense";
    await runMutation(`editor-${editor.kind}`, path, { method: existingId ? "PATCH" : "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(payload) }, `${label} saved.`);
  };

  const deleteEditor = async () => {
    if (!editor?.item || !window.confirm("Delete this planning item?")) return;
    const id = editor.item.id;
    const base = editor.kind === "fixed" ? "/api/fixed-expenses" : editor.kind === "variable" ? "/api/variable-expenses" : editor.kind === "forecast" ? "/api/forecast-items" : "/api/recurring-templates";
    await runMutation(`delete-${editor.kind}-${id}`, `${base}/${id}`, { method: "DELETE", headers: { "content-type": "application/json" }, body: JSON.stringify({ confirm: true }) }, "Planning item removed.");
  };

  const editWorksheetRow = (row: MonthlyQuickPlanningView["quickWorksheetRows"][number]) => {
    if (!data || !row.itemId) return;
    if (row.itemType === "fixed_expense") { const item = data.fixedItems.find((value) => value.id === row.itemId); if (item) setEditor({ kind: "fixed", item }); }
    else if (row.itemType === "variable_expense") { const item = data.variableItems.find((value) => value.id === row.itemId); if (item) setEditor({ kind: "variable", item }); }
    else if (row.itemType === "recurring_template") { const item = data.recurringTemplates.find((value) => value.id === row.itemId); if (item) setEditor({ kind: "recurring", item }); }
    else if (row.itemType === "forecast_item") { const item = data.forecastItems.find((value) => value.id === row.itemId); if (item) setEditor({ kind: "forecast", item }); }
  };

  const saveWorksheetAmount = async (event: FormEvent<HTMLFormElement>, row: MonthlyQuickPlanningView["quickWorksheetRows"][number]) => {
    event.preventDefault();
    if (!row.itemId) return;
    const path = row.itemType === "fixed_expense" ? `/api/fixed-expenses/${row.itemId}` : row.itemType === "variable_expense" ? `/api/variable-expenses/${row.itemId}` : `/api/recurring-templates/${row.itemId}`;
    await runMutation(`amount-${row.itemType}-${row.itemId}`, path, { method: "PATCH", headers: { "content-type": "application/json" }, body: JSON.stringify({ monthlyTarget: numberValue(new FormData(event.currentTarget), "monthlyTarget") }) }, `${row.name} updated.`);
  };

  const saveRole = async (event: FormEvent<HTMLFormElement>, accountId: number) => {
    event.preventDefault(); const form = new FormData(event.currentTarget);
    await runMutation(`account-${accountId}`, `/api/accounts/${accountId}/cash-projection-role`, { method: "PATCH", headers: { "content-type": "application/json" }, body: JSON.stringify({ cashProjectionRole: form.get("role") }) }, "Operating cash account updated.");
  };

  if (loading && !data) return <AuthenticatedPageFrame activePlanSection="tools"><div className={styles.loadingPage}><span className="logo-mark">C</span><strong>Loading Quick Planning...</strong></div></AuthenticatedPageFrame>;
  if (!data) return <div className={styles.loadingPage}><div className={styles.loadError}><TriangleAlert size={24} /><p>{error ?? "We could not load Quick Planning."}</p><button type="button" onClick={() => void loadPlan()}>Try Again</button></div></div>;

  const incomePlanning = featureEnabled(data, "income_planning");
  const cashProjection = featureEnabled(data, "cash_projection");
  const editorTitle = editor?.kind === "fixed" ? `${editor.item ? "Edit" : "Add"} Fixed Expense` : editor?.kind === "variable" ? `${editor.item ? "Edit" : "Add"} Flexible Budget` : editor?.kind === "forecast" ? `${editor.item ? "Edit" : "Plan"} One-Time Expense` : "Edit Recurring Item";

  return (
    <AuthenticatedPageFrame session={data.session} activePlanSection="tools">
      <div className={styles.page}>
        <header className={styles.pageHeader}><div><h1>Quick Planning</h1><p>{data.monthName} current-month cash worksheet.</p></div><div className={styles.monthPill}><CalendarClock size={15} />{data.monthName}</div></header>
        <div className={styles.content}>
          {refreshWarning ? <div className={styles.warning}><TriangleAlert size={18} />{refreshWarning}</div> : null}
          {error ? <div className={styles.error} role="alert"><TriangleAlert size={18} />{error}</div> : null}
          {notice ? <div className={styles.notice} role="status">{notice}</div> : null}
          {busy ? <SavingIndicator /> : null}
          {!canEdit ? <div className={styles.viewerBand}>You have view-only household access. Planning amounts and settings are read-only.</div> : null}

          <div className={styles.layout}>
            <main className={styles.main}>
              <section className={styles.workspace}>
                <header className={styles.sectionHeader}>
                  <div><h2>Current Month Cash Worksheet</h2><p>Start with cash available today, subtract expected expenses, and see the projected month-end balance.</p></div>
                  {canEdit ? <div className={styles.headerActions}><button type="button" onClick={() => setEditor({ kind: "fixed" })}><Plus size={15} />Fixed Expense</button><button type="button" onClick={() => setEditor({ kind: "variable" })}><Plus size={15} />Flexible Budget</button><button type="button" onClick={() => setEditor({ kind: "forecast" })}><Plus size={15} />One-Time Expense</button></div> : null}
                </header>

                {projection ? (
                  <div className={styles.cashPath}>
                    <div className={styles.cashIntro}><span>This Month&apos;s Cash Path</span><p>What you have now, what is still expected to come in, what is expected to go out, and what should be left.</p></div>
                    <div className={styles.cashEquation} aria-label="Current cash plus expected income minus expected expenses equals projected month-end cash">
                      <div><span>Current Operating Cash</span><strong data-negative={projection.balanceAnchor.balance < 0}>{signedCurrency(projection.balanceAnchor.balance)}</strong><small>{projection.balanceAnchor.checkingAccountCount ? `Checking: ${currency(projection.balanceAnchor.checkingBalance)}` : `${projection.balanceAnchor.accountCount} included account${projection.balanceAnchor.accountCount === 1 ? "" : "s"}`}</small></div>
                      <b>+</b><div><span>Expected Money In</span><strong className={styles.positive}>{currency(data.quickCashRemainingIncome)}</strong><small>Remaining scheduled income</small></div>
                      <b>-</b><div><span>Expected Expenses</span><strong className={styles.negative}>{currency(data.quickCashRemainingExpenses)}</strong><small>Remaining bills and spending</small></div>
                      <b>=</b><div className={styles.cashResult}><span>Projected Month-End Cash</span><strong data-negative={projection.endBalance < 0}>{signedCurrency(projection.endBalance)}</strong><small>Projected through {shortDate(projection.endDate)}</small></div>
                    </div>
                    <div className={styles.supportGrid}>
                      <div><span>Next 7 Days</span><strong className={data.quickCashWeekChange < 0 ? styles.negative : styles.positive}>{signedCurrency(data.quickCashWeekChange)}</strong><small>Scheduled activity</small></div>
                      <div><span>7-Day Ending Cash</span><strong data-negative={data.quickCashWeekEndBalance < 0}>{signedCurrency(data.quickCashWeekEndBalance)}</strong><small>Current worksheet timing</small></div>
                      <div><span>Lowest Cash Point</span><strong data-negative={projection.lowestBalance.balance < 0}>{signedCurrency(projection.lowestBalance.balance)}</strong><small>{shortDate(projection.lowestBalance.date)}</small></div>
                      <div className={styles.forecastCta}><strong>Want the next three months?</strong><Link href="/monthly-plan?section=forecast">Open 3-Month Forecast <ChevronRight size={14} /></Link>{cashProjection ? <Link href="/cash-projections">Cash Balance Projections</Link> : <Link href="/settings/billing">Upgrade For Cash Projections</Link>}</div>
                    </div>
                  </div>
                ) : <div className={styles.empty}>Cash projection details are not available yet.</div>}

                {projection?.balanceAnchor.includedAccounts.length ? <div className={styles.accountChips}>{projection.balanceAnchor.includedAccounts.map((account) => <span key={account.id}>{account.name}{account.mask ? ` · ${account.mask}` : ""}: {signedCurrency(account.balance)}</span>)}</div> : null}

                {data.cashProjectionAccountRows.length ? (
                  <details className={styles.accountSettings}>
                    <summary><span><Landmark size={17} />Operating Cash Accounts</span><span>{projection?.balanceAnchor.accountCount ?? 0} Included · Manage</span></summary>
                    <div>{data.cashProjectionAccountRows.map((row) => (
                      <div className={styles.accountRow} key={row.accountId}>
                        <div><strong>{row.name}</strong><span>{row.institution ?? "Connected Account"} · {row.accountType}{row.mask ? ` · ${row.mask}` : ""} · {signedCurrency(row.balance, 2)}</span></div>
                        <div><strong>{row.statusLabel}</strong><span>{row.statusDetail}</span></div>
                        {canEdit ? <form onSubmit={(event) => void saveRole(event, row.accountId)}><select name="role" defaultValue={row.role} aria-label={`Operating cash setting for ${row.name}`}><option value="auto">Auto</option><option value="include">Include</option><option value="exclude">Exclude</option></select><button type="submit" disabled={busy === `account-${row.accountId}`}><Save size={15} /><span>Save</span></button></form> : <span className={styles.roleText}>{row.role}</span>}
                      </div>
                    ))}</div>
                  </details>
                ) : null}

                <div className={styles.worksheetIntro}><strong>Adjust the worksheet below to change the cash path.</strong><span>Editable planned cash updates the matching budget or scheduled expense.</span></div>
                <div className={styles.worksheet}>
                  <div className={styles.tableHeader}>
                    <button type="button" onClick={() => router.push(routeForQuery({ quickSort: query.quickSort === "name_asc" ? "name_desc" : "name_asc" }))}>Upcoming Budget Or Scheduled Expense <ArrowDownUp size={13} /></button>
                    <button type="button" onClick={() => router.push(routeForQuery({ quickSort: query.quickSort === "timing_asc" ? "timing_desc" : "timing_asc" }))}>Timing <ArrowDownUp size={13} /></button>
                    <button type="button" onClick={() => router.push(routeForQuery({ quickSort: query.quickSort === "category_az" ? "category_za" : "category_az" }))}>Category <ArrowDownUp size={13} /></button>
                    <button type="button" onClick={() => router.push(routeForQuery({ quickSort: query.quickSort === "amount_desc" ? "amount_asc" : "amount_desc" }))}>Planned Cash <ArrowDownUp size={13} /></button><span />
                  </div>
                  {data.quickWorksheetRows.map((row, index) => (
                    <div className={styles.worksheetRow} key={`${row.itemType}-${row.itemId ?? index}`}>
                      <div className={styles.itemName}><strong>{row.name}</strong><span>{row.subtitle}</span></div><div className={styles.timing}>{row.timing}</div><Link className={styles.category} href={`/monthly-plan?section=budgets#budget-${encodeURIComponent(row.category.toLowerCase().replaceAll(" ", "-"))}`}>{row.category}</Link>
                      <div className={styles.amountCell}>{canEdit && !row.readonly && row.itemId ? <form onSubmit={(event) => void saveWorksheetAmount(event, row)}><span>$</span><input name="monthlyTarget" type="number" min="0.01" step="0.01" defaultValue={row.amount.toFixed(2)} aria-label={`Planned cash for ${row.name}`} /><button type="submit" disabled={busy === `amount-${row.itemType}-${row.itemId}`} aria-label={`Save planned cash for ${row.name}`}><Save size={14} /></button></form> : <strong>{currency(row.amount, 2)}</strong>}</div>
                      <div className={styles.rowAction}>{row.itemType === "subscription" || row.itemType === "subscriptions" ? <Link href="/subscriptions">{row.actionLabel || "Review"}</Link> : canEdit && row.itemId ? <button type="button" onClick={() => editWorksheetRow(row)}><Pencil size={14} />{row.actionLabel || "Edit"}</button> : null}</div>
                    </div>
                  ))}
                  {!data.quickWorksheetRows.length ? <div className={styles.empty}>Add upcoming bills or flexible budgets to see how they affect this month&apos;s cash position.</div> : null}
                </div>
              </section>

              <details className={styles.baseline}>
                <summary><div><h2>Planning Baseline</h2><p>Adjust income timing only when the current worksheet is using the wrong baseline.</p></div><span>Open</span></summary>
                <div className={styles.baselineBody}>{incomePlanning ? <div className={styles.callout}>Expanded income details live in Income Planning. <Link href="/monthly-plan?section=baseline">Open Income Planning</Link></div> : null}<BaselineForm data={data} canEdit={canEdit} busy={busy === "baseline"} onSave={(payload) => runMutation("baseline", "/api/monthly-plan/baseline", { method: "PATCH", headers: { "content-type": "application/json" }, body: JSON.stringify(payload) }, "Planning baseline saved.").then(() => undefined)} /></div>
              </details>
            </main>

            <aside className={styles.side}>
              <h2>Quick Planning Links</h2>
              <div><span>Review monthly budgets</span><Link href="/monthly-plan?section=budgets">Budgets</Link><strong>{currency(data.totalBudgetPlanned)}</strong></div>
              <div><span>Look beyond this month</span><Link href="/monthly-plan?section=forecast">Forecast</Link><strong>3 Months</strong></div>
              <div><span>Day-by-day cash projections</span><Link href={cashProjection ? "/cash-projections" : "/settings/billing"}>{cashProjection ? "Open" : "Upgrade"}</Link><strong>{cashProjection ? "Available" : "Plan Feature"}</strong></div>
            </aside>
          </div>
        </div>
      </div>

      {editor ? (
        <Modal title={editorTitle} description={editor.kind === "forecast" ? "Add or adjust a one-time expected expense feeding the cash forecast." : "Update the cadence, timing, category, and amount used by Quick Planning."} onClose={() => setEditor(null)}>
          {editor.kind === "fixed" ? <FixedExpenseForm key={`fixed-${editor.item?.id ?? "new"}`} data={data} item={editor.item} busy={Boolean(busy)} onSave={saveEditor} onDelete={editor.item ? deleteEditor : undefined} /> : null}
          {editor.kind === "variable" ? <VariableExpenseForm key={`variable-${editor.item?.id ?? "new"}`} data={data} item={editor.item} busy={Boolean(busy)} onSave={saveEditor} onDelete={editor.item ? deleteEditor : undefined} /> : null}
          {editor.kind === "forecast" ? <><ForecastItemForm key={`forecast-${editor.item?.id ?? "new"}`} data={data} item={editor.item} busy={Boolean(busy)} onSave={saveEditor} onDelete={editor.item ? deleteEditor : undefined} />{!editor.item && forecastExpenses.length ? <div className={styles.existingItems}><h3>One-Time Forecasted Expenses</h3>{forecastExpenses.map((item) => <button type="button" key={item.id} onClick={() => setEditor({ kind: "forecast", item })}><span><strong>{item.description}</strong><small>{shortDate(item.itemDate)} · {item.categoryLabel ?? "Other"}</small></span><strong>{currency(item.amount, 2)}</strong><Pencil size={14} /></button>)}</div> : null}</> : null}
          {editor.kind === "recurring" ? <RecurringTemplateForm key={`recurring-${editor.item.id}`} data={data} item={editor.item} busy={Boolean(busy)} onSave={saveEditor} onDelete={deleteEditor} /> : null}
        </Modal>
      ) : null}
    </AuthenticatedPageFrame>
  );
}
