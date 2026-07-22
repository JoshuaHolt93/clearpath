"use client";

import {
  cashProjectionViewSchema,
  monthlyQuickPlanningViewSchema,
  type CashProjectionView,
  type MonthlyQuickPlanningView,
} from "@clearpath/validation";
import {
  ArrowLeft,
  ArrowRight,
  CalendarDays,
  CalendarPlus,
  Check,
  ChevronDown,
  Clipboard,
  ExternalLink,
  LineChart,
  List,
  Pencil,
  RefreshCw,
  Save,
  Trash2,
  TriangleAlert,
  X,
} from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import QRCode from "qrcode";
import { type FormEvent, type ReactNode, useCallback, useEffect, useMemo, useState } from "react";

import { AuthenticatedPageFrame } from "../authenticated-shell";
import styles from "./cash-projection.module.css";

export type CashProjectionQuery = {
  month: string;
  horizon?: "week" | "1m" | "3m" | "6m" | "custom";
  view: "calendar" | "list" | "graph";
  startDate: string;
  endDate: string;
};

type CashEvent = CashProjectionView["projectionRange"]["events"][number];
type ForecastItem = MonthlyQuickPlanningView["forecastItems"][number];
type RecurringItem = MonthlyQuickPlanningView["recurringTemplates"][number];
type DetectedSchedule = CashProjectionView["detectedRecurring"][number];
type EditTarget =
  | { kind: "forecast"; item: ForecastItem }
  | { kind: "recurring"; item: RecurringItem }
  | { kind: "auto"; item: DetectedSchedule };

const horizonLabels: Record<string, string> = { week: "Week", "1m": "1 Month", "3m": "3 Months", "6m": "6 Months", custom: "Custom" };
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

function dateLabel(value: string, weekday = false): string {
  return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", ...(weekday ? { weekday: "short" as const } : {}), timeZone: "UTC" }).format(new Date(`${value}T00:00:00Z`));
}

function dateTimeLabel(value: string): string {
  return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" }).format(new Date(value));
}

function routeForQuery(query: CashProjectionQuery): string {
  const params = new URLSearchParams();
  if (query.month) params.set("month", query.month);
  if (query.horizon) params.set("horizon", query.horizon);
  if (query.view !== "calendar") params.set("view", query.view);
  if (query.horizon === "custom" && query.startDate) params.set("start_date", query.startDate);
  if (query.horizon === "custom" && query.endDate) params.set("end_date", query.endDate);
  const encoded = params.toString();
  return `/cash-projections${encoded ? `?${encoded}` : ""}`;
}

function apiRouteForQuery(query: CashProjectionQuery): string {
  return `/api${routeForQuery(query)}`;
}

function queryBody(query: CashProjectionQuery) {
  return {
    month: query.month || null,
    horizon: query.horizon ?? null,
    view: query.view,
    startDate: query.horizon === "custom" ? query.startDate || null : null,
    endDate: query.horizon === "custom" ? query.endDate || null : null,
  };
}

async function responseMessage(response: Response, fallback: string): Promise<string> {
  const payload = await response.json().catch(() => null);
  return payload && typeof payload.message === "string" ? payload.message : fallback;
}

function splitNumbers(value: string | null): number[] {
  return (value ?? "").split(",").map(Number).filter(Number.isInteger);
}

function nullableString(form: FormData, name: string): string | null {
  return String(form.get(name) ?? "").trim() || null;
}

function Modal({ title, subtitle, children, onClose, wide = false }: { title: string; subtitle: string; children: ReactNode; onClose(): void; wide?: boolean }) {
  return (
    <div className={styles.modalShell} role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className={`${styles.modalPanel} ${wide ? styles.modalWide : ""}`} role="dialog" aria-modal="true" aria-labelledby="cash-modal-title">
        <header><div><h2 id="cash-modal-title">{title}</h2><p>{subtitle}</p></div><button type="button" className={styles.iconButton} aria-label="Close" onClick={onClose}><X size={18} /></button></header>
        <div className={styles.modalBody}>{children}</div>
      </section>
    </div>
  );
}

function ChoiceGrid({ options, name, selected, full = false }: { options: Record<string, string>; name: string; selected: number[]; full?: boolean }) {
  return <div className={styles.choiceGrid}>{Object.entries(options).map(([value, label]) => <label key={value}><input type="checkbox" name={name} value={value} defaultChecked={selected.includes(Number(value))} /><span>{full ? label : label.slice(0, 3)}</span></label>)}</div>;
}

function CadenceFields({ plan, frequency, item }: { plan: MonthlyQuickPlanningView; frequency: string; item?: RecurringItem }) {
  return (
    <>
      {frequency === "weekly" || frequency === "biweekly" ? <div className={styles.choiceField}><span>Days Of Week</span><ChoiceGrid options={plan.weekdayOptions} name="daysOfWeek" selected={splitNumbers(item?.daysOfWeek ?? null)} /></div> : null}
      {frequency === "semimonthly" ? <label>Second Date<input name="secondDate" type="date" defaultValue={item?.secondDate ?? ""} /></label> : null}
      {frequency === "monthly" || frequency === "semimonthly" ? (
        <div className={styles.formGrid}>
          <label>Weekday Pattern<select name="monthlyWeekday" defaultValue={item?.monthlyWeekday ?? ""}><option value="">Calendar Date</option>{Object.entries(plan.weekdayOptions).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
          <div className={styles.choiceField}><span>Weeks In Month</span><ChoiceGrid options={plan.monthlyWeekOptions} name="monthlyWeeks" selected={splitNumbers(item?.monthlyWeekNumbers ?? null)} full /></div>
        </div>
      ) : null}
    </>
  );
}

function ForecastEditor({ plan, item, busy, onSave, onDelete }: { plan: MonthlyQuickPlanningView; item: ForecastItem; busy: boolean; onSave(payload: Record<string, unknown>): Promise<void>; onDelete(): Promise<void> }) {
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    await onSave({ itemDate: nullableString(form, "itemDate"), description: nullableString(form, "description"), amount: Number(form.get("amount") ?? 0), itemType: nullableString(form, "itemType"), categoryLabel: nullableString(form, "categoryLabel"), notes: nullableString(form, "notes") });
  };
  return (
    <form className={styles.formStack} onSubmit={submit}>
      <div className={styles.formGrid}>
        <label>Date<input name="itemDate" type="date" defaultValue={item.itemDate} required /></label>
        <label>Type<select name="itemType" defaultValue={item.itemType}><option value="expense">Expense</option><option value="income">Income</option></select></label>
        <label>Description<input name="description" defaultValue={item.description} required /></label>
        <label>Amount<input name="amount" type="number" min="0.01" step="0.01" defaultValue={item.amount} required /></label>
        <label>Category Label<input name="categoryLabel" list="cash-category-options" defaultValue={item.categoryLabel ?? ""} /></label>
        <label>Notes<input name="notes" defaultValue={item.notes ?? ""} /></label>
      </div>
      <datalist id="cash-category-options">{plan.categoryLabelOptions.map((label) => <option key={label} value={label} />)}</datalist>
      <div className={styles.formActions}><button type="submit" disabled={busy}><Save size={16} />Save Planned Item</button><button type="button" className={styles.dangerButton} disabled={busy} onClick={() => void onDelete()}><Trash2 size={16} />Remove Planned Item</button></div>
    </form>
  );
}

function RecurringEditor({ plan, item, busy, onSave, onDelete }: { plan: MonthlyQuickPlanningView; item: RecurringItem; busy: boolean; onSave(payload: Record<string, unknown>): Promise<void>; onDelete(): Promise<void> }) {
  const [frequency, setFrequency] = useState(item.frequency);
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const incomeAdjustment = Boolean(item.incomeBasis || item.incomeType || item.incomeNextPayDate);
    await onSave({
      name: nullableString(form, "name"), amount: Number(form.get("amount") ?? 0), itemType: nullableString(form, "itemType"), frequency,
      startDate: nullableString(form, "startDate"), secondDate: nullableString(form, "secondDate"), recurringDaysOfWeek: form.getAll("daysOfWeek").map(Number),
      recurringMonthlyWeekNumbers: form.getAll("monthlyWeeks").map(Number), recurringMonthlyWeekday: nullableString(form, "monthlyWeekday") === null ? null : Number(form.get("monthlyWeekday")),
      categoryLabel: nullableString(form, "categoryLabel"), notes: nullableString(form, "notes"), incomeAdjustment,
      incomeReplacement: item.incomeReplacement, incomeBasis: item.incomeBasis ?? undefined, incomeType: item.incomeType ?? undefined,
      paycheckCadence: item.paycheckCadence ?? undefined, incomeNextPayDate: item.incomeNextPayDate,
      incomeAmount: item.amount, hourlyHoursPerWeek: item.hourlyHoursPerWeek, additionalIncomeAmount: item.additionalIncomeAmount,
      additionalIncomeFrequency: item.additionalIncomeFrequency, taxState: item.taxState, taxFilingStatus: item.taxFilingStatus,
      includePayrollTaxes: item.includePayrollTaxes,
    });
  };
  return (
    <form className={styles.formStack} onSubmit={submit}>
      <div className={styles.formGrid}>
        <label>Description<input name="name" defaultValue={item.name} required /></label>
        <label>Amount<input name="amount" type="number" min="0.01" step="0.01" defaultValue={item.amount} required /></label>
        <label>Type<select name="itemType" defaultValue={item.itemType}><option value="expense">Expense</option><option value="income">Income</option></select></label>
        <label>Cadence<select value={frequency} onChange={(event) => setFrequency(event.target.value)}>{Object.entries(Object.keys(plan.recurringFrequencyOptions).length ? plan.recurringFrequencyOptions : frequencyFallback).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label>First Expected Date<input name="startDate" type="date" defaultValue={item.startDate} required /></label>
        <label>Category Label<input name="categoryLabel" list="cash-category-options" defaultValue={item.categoryLabel ?? ""} /></label>
      </div>
      <CadenceFields plan={plan} frequency={frequency} item={item} />
      <label>Notes<input name="notes" defaultValue={item.notes ?? ""} /></label>
      <div className={styles.formActions}><button type="submit" disabled={busy}><Save size={16} />Update Future Occurrences</button><button type="button" className={styles.dangerButton} disabled={busy} onClick={() => void onDelete()}><Trash2 size={16} />Remove Recurring Schedule</button></div>
    </form>
  );
}

function AutoRecurringEditor({ plan, item, busy, onSave, onIgnore }: { plan: MonthlyQuickPlanningView; item: DetectedSchedule; busy: boolean; onSave(payload: Record<string, unknown>): Promise<void>; onIgnore(): Promise<void> }) {
  const [frequency, setFrequency] = useState(item.frequency);
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    await onSave({
      action: "save", name: nullableString(form, "name"), amount: Number(form.get("amount") ?? 0), frequency,
      scheduleStartDate: nullableString(form, "startDate"), secondDate: nullableString(form, "secondDate"), recurringDaysOfWeek: form.getAll("daysOfWeek").map(Number),
      recurringMonthlyWeekNumbers: form.getAll("monthlyWeeks").map(Number), recurringMonthlyWeekday: nullableString(form, "monthlyWeekday") === null ? null : Number(form.get("monthlyWeekday")),
      categoryLabel: nullableString(form, "categoryLabel"), notes: nullableString(form, "notes"),
    });
  };
  const weekday = new Date(`${item.startDate}T00:00:00Z`).getUTCDay();
  return (
    <form className={styles.formStack} onSubmit={submit}>
      <div className={styles.formGrid}>
        <label>Name<input name="name" defaultValue={item.name} required /></label>
        <label>Amount<input name="amount" type="number" min="0.01" step="0.01" defaultValue={item.amount} required /></label>
        <label>First Expected Date<input name="startDate" type="date" defaultValue={item.startDate} required /></label>
        <label>Cadence<select value={frequency} onChange={(event) => setFrequency(event.target.value)}>{Object.entries(Object.keys(plan.recurringFrequencyOptions).length ? plan.recurringFrequencyOptions : frequencyFallback).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label>Category Label<input name="categoryLabel" list="cash-category-options" defaultValue={item.categoryLabel ?? ""} /></label>
        <label>Notes<input name="notes" defaultValue={item.notes ?? ""} /></label>
      </div>
      {frequency === "weekly" || frequency === "biweekly" ? <div className={styles.choiceField}><span>Days Of Week</span><ChoiceGrid options={plan.weekdayOptions} name="daysOfWeek" selected={[weekday === 0 ? 6 : weekday - 1]} /></div> : null}
      {frequency === "semimonthly" ? <label>Second Date<input name="secondDate" type="date" /></label> : null}
      {frequency === "monthly" || frequency === "semimonthly" ? <div className={styles.formGrid}><label>Weekday Pattern<select name="monthlyWeekday" defaultValue=""><option value="">Calendar Date</option>{Object.entries(plan.weekdayOptions).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><div className={styles.choiceField}><span>Weeks In Month</span><ChoiceGrid options={plan.monthlyWeekOptions} name="monthlyWeeks" selected={[]} full /></div></div> : null}
      <div className={styles.formActions}><button type="submit" disabled={busy}><Save size={16} />Save Adjusted Schedule</button><button type="button" className={styles.dangerButton} disabled={busy} onClick={() => void onIgnore()}><Trash2 size={16} />Exclude From Projection</button></div>
    </form>
  );
}

function EventActions({ event, canEdit, onEdit, onDelete }: { event: CashEvent; canEdit: boolean; onEdit(event: CashEvent): void; onDelete(event: CashEvent): void }) {
  if (event.source === "paycheck") return <Link className={styles.inlineAction} href={event.sourceId ? `/monthly-plan?section=baseline#future-income-adjustment-${event.sourceId}` : "/monthly-plan?section=baseline"}>Adjust Income</Link>;
  if (!canEdit || !event.sourceId) return null;
  if (["one_time", "recurring", "auto_recurring"].includes(event.source)) return <button type="button" className={styles.inlineAction} onClick={() => onEdit(event)}><Pencil size={13} />Edit Schedule</button>;
  if (["fixed", "variable"].includes(event.source)) return <button type="button" className={`${styles.inlineAction} ${styles.dangerLink}`} onClick={() => onDelete(event)}><Trash2 size={13} />Delete Schedule</button>;
  return null;
}

function CashEventRow({ event, canEdit, onEdit, onDelete }: { event: CashEvent; canEdit: boolean; onEdit(event: CashEvent): void; onDelete(event: CashEvent): void }) {
  return (
    <div className={styles.eventRow} data-income={event.itemType === "income"}>
      <span><strong>{event.description}</strong><small>{event.source === "actual" ? "Actual" : "Scheduled"}{event.source === "actual" && event.accountName ? ` - ${event.accountName}` : ""}</small></span>
      <span className={styles.eventSide}><strong>{event.itemType === "income" ? "+" : "-"}{currency(event.amount)}</strong><EventActions event={event} canEdit={canEdit} onEdit={onEdit} onDelete={onDelete} /></span>
    </div>
  );
}

function CalendarView({ data, canEdit, onEdit, onDelete }: { data: CashProjectionView; canEdit: boolean; onEdit(event: CashEvent): void; onDelete(event: CashEvent): void }) {
  return <div className={styles.calendarMonths}>{data.projectionRange.projections.map((month) => (
    <section className={styles.projectionPanel} key={month.month}>
      <header className={styles.panelHeader}><h2>{month.monthLabel}</h2><span>{month.events.length} Events</span></header>
      <div className={styles.calendarScroller}>
        <div className={styles.weekdays}>{["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map((label) => <span key={label}>{label}</span>)}</div>
        <div className={styles.calendarGrid}>{month.calendarCells.map((day, index) => day ? (
          <article className={styles.cashDay} data-today={day.isToday} data-negative={day.endingBalance < 0} key={day.date}>
            <header><span><strong>{dateLabel(day.date)}</strong><small>{day.balanceBasis}</small></span><span><strong>{day.endingBalance < 0 ? "-" : ""}{currency(day.endingBalance)}</strong>{day.actualBalance !== null && day.scheduledEvents.length ? <small>Current {currency(day.actualBalance)}</small> : null}</span></header>
            {day.events.length ? <div className={styles.dayEvents}>{day.events.slice(0, 3).map((event, eventIndex) => <CashEventRow key={`${event.source}-${event.sourceId ?? eventIndex}`} event={event} canEdit={canEdit} onEdit={onEdit} onDelete={onDelete} />)}{day.events.length > 3 ? <details><summary>+{day.events.length - 3} more cash item{day.events.length - 3 === 1 ? "" : "s"}</summary>{day.events.slice(3).map((event, eventIndex) => <CashEventRow key={`${event.source}-${event.sourceId ?? eventIndex}`} event={event} canEdit={canEdit} onEdit={onEdit} onDelete={onDelete} />)}</details> : null}</div> : null}
          </article>
        ) : <div className={styles.emptyDay} key={`empty-${index}`} />)}</div>
      </div>
    </section>
  ))}</div>;
}

function ListView({ data, canEdit, onEdit, onDelete }: { data: CashProjectionView; canEdit: boolean; onEdit(event: CashEvent): void; onDelete(event: CashEvent): void }) {
  return <section className={styles.projectionPanel}><header className={styles.panelHeader}><h2>Daily Cash Balances</h2></header><div className={styles.cashList}>{data.projectionRange.days.map((day) => <article key={day.date} data-negative={day.endingBalance < 0}><div><strong>{dateLabel(day.date, true)}</strong><small>Net {signedCurrency(day.netChange)}{day.events.length ? ` - ${day.events.length} event${day.events.length === 1 ? "" : "s"}` : ""}</small>{day.events.length ? <details><summary>{day.events.length} cash item{day.events.length === 1 ? "" : "s"}</summary>{day.events.map((event, index) => <CashEventRow key={`${event.source}-${event.sourceId ?? index}`} event={event} canEdit={canEdit} onEdit={onEdit} onDelete={onDelete} />)}</details> : null}</div><div className={styles.listBalance}><span>{day.balanceBasis} Cash</span><strong>{day.endingBalance < 0 ? "-" : ""}{currency(day.endingBalance)}</strong>{day.actualBalance !== null && day.scheduledEvents.length ? <small>Current Check {currency(day.actualBalance)}</small> : null}</div></article>)}</div></section>;
}

function GraphView({ data }: { data: CashProjectionView }) {
  const graph = data.projectionRange.graph;
  return (
    <section className={styles.projectionPanel}>
      <header className={styles.panelHeader}><h2>Projected Cash Balance Graph</h2><span>{graph.showZeroLine ? "$0 Baseline" : "Scale Includes $0"}</span></header>
      <div className={styles.graphWrap}>
        <span className={styles.graphMax}>{currency(graph.maxValue)}</span>
        <svg viewBox="0 0 100 100" preserveAspectRatio="none" role="img" aria-label="Projected cash balance line graph">
          {graph.monthMarkers.map((marker) => <line key={marker.label} className={styles.monthLine} x1={marker.xPct} x2={marker.xPct} y1="0" y2="92" />)}
          {graph.showZeroLine ? <line className={styles.zeroLine} x1="0" x2="100" y1={graph.zeroAxisPct} y2={graph.zeroAxisPct} /> : null}
          <polyline className={styles.graphLine} points={graph.points} />
          {graph.pointRows.map((point) => <circle className={styles.graphPoint} key={`${point.dateLabel}-${point.xPct}`} cx={point.xPct} cy={point.yPct} r="1.4"><title>{point.dateLabel}: {currency(point.balance)} {point.balanceBasis.toLowerCase()} cash</title></circle>)}
        </svg>
        {graph.showZeroLine ? <span className={styles.graphZero} style={{ top: `${graph.zeroAxisPct}%` }}>$0</span> : null}
      </div>
      <div className={styles.graphAxis}><span>{dateLabel(data.projectionRange.startDate)}</span>{graph.monthMarkers.map((marker) => <span key={marker.label} style={{ left: `${marker.xPct}%` }}>{marker.axisLabel}</span>)}<span>{dateLabel(data.projectionRange.endDate)}</span></div>
    </section>
  );
}

function CalendarSync({ data, canEdit, busy, qrCode, copied, onAction, onCopy }: { data: CashProjectionView; canEdit: boolean; busy: boolean; qrCode: string; copied: boolean; onAction(action: "enable" | "reset" | "disable"): void; onCopy(): void }) {
  const feed = data.calendarFeed;
  return (
    <details className={styles.settingsPanel}>
      <summary><span><CalendarPlus size={18} /><strong>Calendar Sync</strong></span><span>{feed.enabled ? "Enabled" : "Private Feed"}<ChevronDown size={16} /></span></summary>
      <div className={styles.settingsBody}>
        {feed.enabled ? <>
          <div className={styles.syncLayout}><div><h3>Subscribe To Daily Cash Balances</h3><p>This private, read-only feed includes recent actual cash-balance history, daily projections, and scheduled movements.</p>{feed.generatedAt ? <small>Link generated {dateTimeLabel(feed.generatedAt)}</small> : null}</div><div className={styles.syncActions}>{feed.googleUrl ? <a href={feed.googleUrl} target="_blank" rel="noreferrer">Google Calendar<ExternalLink size={14} /></a> : null}{feed.webcalUrl ? <a href={feed.webcalUrl}>Apple Calendar<ExternalLink size={14} /></a> : null}{feed.feedUrl ? <a href={feed.feedUrl}>Download ICS</a> : null}</div></div>
          {qrCode ? <div className={styles.mobileHandoff}><div><h3>Subscribe From Your Phone</h3><p>Scan the private subscription link with your phone camera.</p></div><Image src={qrCode} alt="QR code for the private ClearPath cash balance calendar feed" width={122} height={122} unoptimized /></div> : null}
          {feed.feedUrl ? <div className={styles.copyRow}><input aria-label="Calendar Feed URL" value={feed.feedUrl} readOnly /><button type="button" onClick={onCopy}>{copied ? <Check size={16} /> : <Clipboard size={16} />}{copied ? "Copied" : "Copy Link"}</button></div> : null}
          {canEdit ? <div className={styles.secondaryActions}><button type="button" disabled={busy} onClick={() => onAction("reset")}>Reset Private Link</button><button type="button" disabled={busy} onClick={() => onAction("disable")}>Disable Sync</button></div> : null}
        </> : <div className={styles.syncLayout}><div><h3>Send Projected Cash Balances To Your Calendar</h3><p>Generate a private subscription link for actual cash history, scheduled income, recurring expenses, and one-time planned items.</p></div>{canEdit ? <button type="button" className={styles.primaryButton} disabled={busy} onClick={() => onAction("enable")}><CalendarPlus size={16} />Enable Calendar Sync</button> : null}</div>}
      </div>
    </details>
  );
}

export function CashProjectionWorkspace({ query }: { query: CashProjectionQuery }) {
  const router = useRouter();
  const [data, setData] = useState<CashProjectionView | null>(null);
  const [plan, setPlan] = useState<MonthlyQuickPlanningView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [editing, setEditing] = useState<EditTarget | null>(null);
  const [qrCode, setQrCode] = useState("");
  const [copied, setCopied] = useState(false);

  const load = useCallback(async (quiet = false) => {
    if (!quiet) setError(null);
    try {
      const [projectionResponse, planResponse] = await Promise.all([
        fetch(apiRouteForQuery(query), { cache: "no-store" }),
        fetch("/api/monthly-plan?section=tools", { cache: "no-store" }),
      ]);
      if (!projectionResponse.ok) throw new Error(await responseMessage(projectionResponse, "We could not load cash balance projections."));
      if (!planResponse.ok) throw new Error(await responseMessage(planResponse, "We could not load projection schedules."));
      const projectionParsed = cashProjectionViewSchema.safeParse(await projectionResponse.json());
      const planParsed = monthlyQuickPlanningViewSchema.safeParse(await planResponse.json());
      if (!projectionParsed.success || !planParsed.success) throw new Error("Cash projection data did not match the expected contract.");
      setData(projectionParsed.data);
      setPlan(planParsed.data);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "We could not load cash balance projections.");
    }
  }, [query]);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    const value = data?.calendarFeed.webcalUrl ?? data?.calendarFeed.feedUrl;
    if (!value) { setQrCode(""); return; }
    let active = true;
    void QRCode.toDataURL(value, { width: 152, margin: 1, color: { dark: "#14324b", light: "#ffffff" } }).then((uri) => { if (active) setQrCode(uri); }).catch(() => { if (active) setQrCode(""); });
    return () => { active = false; };
  }, [data?.calendarFeed.feedUrl, data?.calendarFeed.webcalUrl]);

  const canEdit = Boolean(plan && plan.session.subject.householdRole !== "viewer");
  const currentQuery = useMemo<CashProjectionQuery>(() => data ? {
    month: data.projectionRange.startMonth.slice(0, 7),
    horizon: data.horizon,
    view: data.view,
    startDate: data.customStart,
    endDate: data.customEnd,
  } : query, [data, query]);

  const navigate = (patch: Partial<CashProjectionQuery>) => router.push(routeForQuery({ ...currentQuery, ...patch }));

  const saveHorizon = async (horizon: CashProjectionQuery["horizon"]) => {
    if (horizon !== "custom" && canEdit) {
      const response = await fetch("/api/cash-projections/preferences", { method: "PATCH", headers: { "content-type": "application/json" }, body: JSON.stringify({ defaultHorizon: horizon }) });
      if (!response.ok) setError(await responseMessage(response, "We could not save that time horizon."));
    }
    navigate({ horizon });
  };

  const refreshBalances = async () => {
    setBusy("refresh"); setError(null); setNotice(null);
    try {
      const response = await fetch("/api/cash-projections/refresh", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(queryBody(currentQuery)) });
      if (!response.ok) throw new Error(await responseMessage(response, "We could not refresh connected balances."));
      const parsed = cashProjectionViewSchema.safeParse(await response.json());
      if (!parsed.success) throw new Error("Refreshed cash projection data did not match the expected contract.");
      setData(parsed.data);
      const synced = parsed.data.refresh?.synced ?? 0;
      const errors = parsed.data.refresh?.errors ?? [];
      setNotice(errors.length ? `Refreshed ${synced} connected item${synced === 1 ? "" : "s"}. ${errors.join(" ")}` : `Refreshed ${synced} connected item${synced === 1 ? "" : "s"}.`);
    } catch (caught) { setError(caught instanceof Error ? caught.message : "We could not refresh connected balances."); }
    finally { setBusy(null); }
  };

  const resourceMutation = async (url: string, method: "PATCH" | "DELETE", body: Record<string, unknown>, success: string) => {
    setBusy(url); setError(null); setNotice(null);
    try {
      const response = await fetch(url, { method, headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
      if (!response.ok) throw new Error(await responseMessage(response, "We could not update that projection schedule."));
      setEditing(null); setNotice(success); await load(true);
    } catch (caught) { setError(caught instanceof Error ? caught.message : "We could not update that projection schedule."); }
    finally { setBusy(null); }
  };

  const editEvent = (event: CashEvent) => {
    if (!plan || event.sourceId === null) return;
    if (event.source === "one_time") {
      const item = plan.forecastItems.find((row) => row.id === Number(event.sourceId));
      if (item) setEditing({ kind: "forecast", item });
    } else if (event.source === "recurring") {
      const item = plan.recurringTemplates.find((row) => row.id === Number(event.sourceId));
      if (item) setEditing({ kind: "recurring", item });
    } else if (event.source === "auto_recurring") {
      const item = data?.detectedRecurring.find((row) => row.detectionKey === String(event.sourceId));
      if (item) setEditing({ kind: "auto", item });
    }
  };

  const deleteEvent = (event: CashEvent) => {
    if (!event.sourceId || !["fixed", "variable"].includes(event.source)) return;
    if (!window.confirm(`Delete this ${event.source === "fixed" ? "recurring" : "variable"} projected cash schedule?`)) return;
    void resourceMutation(`/api/${event.source === "fixed" ? "fixed-expenses" : "variable-expenses"}/${event.sourceId}`, "DELETE", { confirm: true }, "Projected cash schedule removed.");
  };

  const updateAuto = async (item: DetectedSchedule, payload: Record<string, unknown>) => {
    setBusy("auto"); setError(null); setNotice(null);
    try {
      const response = await fetch(`/api/cash-projections/auto-recurring/${encodeURIComponent(item.detectionKey)}`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ ...queryBody(currentQuery), ...payload }) });
      if (!response.ok) throw new Error(await responseMessage(response, "We could not update that detected recurring charge."));
      const parsed = cashProjectionViewSchema.safeParse(await response.json());
      if (!parsed.success) throw new Error("Updated cash projection data did not match the expected contract.");
      setData(parsed.data); setEditing(null); setNotice(payload.action === "ignore" ? "Detected charge excluded from projections." : "Detected charge saved as a managed recurring schedule."); await load(true);
    } catch (caught) { setError(caught instanceof Error ? caught.message : "We could not update that detected recurring charge."); }
    finally { setBusy(null); }
  };

  const updateCalendar = async (action: "enable" | "reset" | "disable") => {
    if ((action === "reset" || action === "disable") && !window.confirm(action === "reset" ? "Reset this private calendar link? Existing subscriptions will stop updating." : "Disable calendar sync? Existing subscriptions will stop updating.")) return;
    setBusy("calendar"); setError(null);
    try {
      const response = await fetch("/api/cash-projections/calendar-feed", { method: "PATCH", headers: { "content-type": "application/json" }, body: JSON.stringify({ action }) });
      if (!response.ok) throw new Error(await responseMessage(response, "We could not update calendar sync."));
      const feed = await response.json();
      setData((current) => current ? { ...current, calendarFeed: feed } : current);
      setNotice(action === "disable" ? "Calendar sync disabled." : action === "reset" ? "Private calendar link reset." : "Calendar sync enabled.");
    } catch (caught) { setError(caught instanceof Error ? caught.message : "We could not update calendar sync."); }
    finally { setBusy(null); }
  };

  const saveAccountRole = async (accountId: number, role: string) => {
    await resourceMutation(`/api/accounts/${accountId}/cash-projection-role`, "PATCH", { cashProjectionRole: role }, "Operating-cash setting updated.");
  };

  const copyFeed = async () => {
    const value = data?.calendarFeed.feedUrl;
    if (!value) return;
    await navigator.clipboard.writeText(value);
    setCopied(true); window.setTimeout(() => setCopied(false), 2000);
  };

  if (!data || !plan) return <AuthenticatedPageFrame activePlanSection="tools"><div className={styles.loadingPage}><span className="logo-mark">C</span>{error ? <div><TriangleAlert size={22} /><p>{error}</p><button type="button" onClick={() => void load()}>Try Again</button></div> : <strong>Loading Cash Balance Projections...</strong>}</div></AuthenticatedPageFrame>;

  const range = data.projectionRange;
  const monthValue = range.startMonth.slice(0, 7);
  const previousQuery = { ...currentQuery, month: data.previousMonth.slice(0, 7) };
  const nextQuery = { ...currentQuery, month: data.nextMonth.slice(0, 7) };

  return (
    <AuthenticatedPageFrame session={plan.session}>
      <div className={styles.page}>
        <header className={styles.pageHeader}><div><h1>Cash Balance Projections</h1><p>Scheduled cash movement with separate foresight signals for variable-spend risk.</p></div><div className={styles.headerActions}>{canEdit ? <button type="button" disabled={busy === "refresh"} onClick={() => void refreshBalances()}><RefreshCw size={16} className={busy === "refresh" ? styles.spinning : ""} />{busy === "refresh" ? "Refreshing..." : "Refresh Balances"}</button> : null}<Link href={routeForQuery(previousQuery)} aria-label="Previous projection period"><ArrowLeft size={16} />Previous</Link><Link href={routeForQuery(nextQuery)} aria-label="Next projection period">Next<ArrowRight size={16} /></Link></div></header>
        <div className={styles.content}>
          {error ? <div className={styles.error} role="alert"><TriangleAlert size={18} />{error}</div> : null}
          {notice ? <div className={styles.notice} role="status"><Check size={18} />{notice}</div> : null}
          {!canEdit ? <div className={styles.viewerBand}>You have view-only household access. Projection settings and schedules are read-only.</div> : null}

          <div className={styles.explainer}>Past and current balances use posted transactions. Future balances use saved schedules, one-time items, income timing, and recurring transaction patterns.</div>

          <section className={styles.controls} aria-label="Projection controls">
            <label>Start Month<input type="month" value={monthValue} min={data.projectionMinMonth} max={data.projectionMaxMonth} onChange={(event) => navigate({ month: event.target.value })} /></label>
            <div className={styles.segmentField}><span>View</span><div className={styles.segmented} role="group" aria-label="Projection View"><button type="button" aria-pressed={data.view === "calendar"} onClick={() => navigate({ view: "calendar" })}><CalendarDays size={15} />Calendar</button><button type="button" aria-pressed={data.view === "list"} onClick={() => navigate({ view: "list" })}><List size={15} />List</button><button type="button" aria-pressed={data.view === "graph"} onClick={() => navigate({ view: "graph" })}><LineChart size={15} />Graph</button></div></div>
            <label>Time Horizon<select value={data.horizon} onChange={(event) => void saveHorizon(event.target.value as CashProjectionQuery["horizon"])}>{Object.entries(horizonLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
            {data.horizon === "custom" ? <><label>Custom Start<input type="date" value={data.customStart} min={data.customMinDate} max={data.customMaxDate} onChange={(event) => navigate({ startDate: event.target.value })} /></label><label>Custom End<input type="date" value={data.customEnd} min={data.customMinDate} max={data.customMaxDate} onChange={(event) => navigate({ endDate: event.target.value })} /></label></> : null}
          </section>

          <section className={styles.summaryGrid} aria-label="Projection summary">
            <article><span>Time Horizon</span><strong>{dateLabel(range.startDate)} - {dateLabel(range.endDate)}</strong></article>
            <article><span>Opening Balance</span><strong>{range.startBalance < 0 ? "-" : ""}{currency(range.startBalance)}</strong></article>
            <article><span>Current Operating Cash</span><strong>{range.balanceAnchor.balance < 0 ? "-" : ""}{currency(range.balanceAnchor.balance)}</strong><small>{range.balanceAnchor.checkingAccountCount ? `Checking: ${currency(range.balanceAnchor.checkingBalance)}` : `${range.balanceAnchor.accountCount} included account${range.balanceAnchor.accountCount === 1 ? "" : "s"}`}</small></article>
            <article><span>Projected Ending Balance</span><strong>{range.endBalance < 0 ? "-" : ""}{currency(range.endBalance)}</strong></article>
            <article data-negative={range.lowestBalance.balance < 0}><span>Lowest Balance</span><strong>{range.lowestBalance.balance < 0 ? "-" : ""}{currency(range.lowestBalance.balance)}</strong><small>{dateLabel(range.lowestBalance.date)}</small></article>
          </section>

          {data.accountRows.length ? <details className={styles.settingsPanel} id="operating-cash-accounts"><summary><span><strong>Operating Cash Accounts</strong></span><span>{range.balanceAnchor.accountCount} Included<ChevronDown size={16} /></span></summary><div className={styles.accountList}>{data.accountRows.map((account) => <article key={account.accountId}><div><strong>{account.name}</strong><small>{account.institution ?? "Connected Account"} - {account.accountType}{account.mask ? ` - ${account.mask}` : ""} - {account.balance < 0 ? "-" : ""}{currency(account.balance, 2)}</small></div><div className={styles.accountStatus}><span data-included={account.included}>{account.statusLabel}</span><small>{account.statusDetail}</small></div>{canEdit ? <form onSubmit={(event) => { event.preventDefault(); const form = new FormData(event.currentTarget); void saveAccountRole(account.accountId, String(form.get("role"))); }}><select name="role" defaultValue={account.role} aria-label={`Cash projection setting for ${account.name}`}><option value="auto">Auto</option><option value="include">Include</option><option value="exclude">Exclude</option></select><button type="submit" disabled={Boolean(busy)}>Save</button></form> : null}</article>)}</div></details> : null}

          <CalendarSync data={data} canEdit={canEdit} busy={busy === "calendar"} qrCode={qrCode} copied={copied} onAction={(action) => void updateCalendar(action)} onCopy={() => void copyFeed()} />

          <section className={styles.foresight}><header><strong>Foresight Layer</strong><span>Does Not Change Projection</span></header><p>{data.projection.trend.message} Current tracked variable spend is {currency(data.projection.trend.currentVariableSpend)} against a monthly plan of {currency(data.projection.trend.plannedVariableSpend)}.</p></section>

          {data.view === "calendar" ? <CalendarView data={data} canEdit={canEdit} onEdit={editEvent} onDelete={deleteEvent} /> : data.view === "list" ? <ListView data={data} canEdit={canEdit} onEdit={editEvent} onDelete={deleteEvent} /> : <GraphView data={data} />}

          {data.ignoredRecurring.length ? <details className={styles.ignoredPanel}><summary>Excluded recurring patterns ({data.ignoredRecurring.length})</summary><div>{data.ignoredRecurring.map((item) => <span key={item.id}><strong>{item.name}</strong>{currency(item.amount, 2)} - {item.frequency}</span>)}</div></details> : null}
        </div>
      </div>

      {editing?.kind === "forecast" ? <Modal title="Edit Planned Cash Item" subtitle={editing.item.description} onClose={() => setEditing(null)}><ForecastEditor plan={plan} item={editing.item} busy={Boolean(busy)} onSave={(payload) => resourceMutation(`/api/forecast-items/${editing.item.id}`, "PATCH", payload, "Planned cash item updated.")} onDelete={async () => { if (window.confirm("Remove this planned cash item from Cash Balance Projections?")) await resourceMutation(`/api/forecast-items/${editing.item.id}`, "DELETE", { confirm: true }, "Planned cash item removed."); }} /></Modal> : null}
      {editing?.kind === "recurring" ? <Modal title="Edit Recurring Forecast Schedule" subtitle={editing.item.name} wide onClose={() => setEditing(null)}><RecurringEditor plan={plan} item={editing.item} busy={Boolean(busy)} onSave={(payload) => resourceMutation(`/api/recurring-templates/${editing.item.id}`, "PATCH", payload, "Recurring forecast schedule updated.")} onDelete={async () => { if (window.confirm("Remove this recurring forecast schedule and its future projected cash items?")) await resourceMutation(`/api/recurring-templates/${editing.item.id}`, "DELETE", { confirm: true }, "Recurring forecast schedule removed."); }} /></Modal> : null}
      {editing?.kind === "auto" ? <Modal title="Edit Detected Recurring Expense" subtitle={editing.item.name} wide onClose={() => setEditing(null)}><AutoRecurringEditor plan={plan} item={editing.item} busy={Boolean(busy)} onSave={(payload) => updateAuto(editing.item, payload)} onIgnore={() => updateAuto(editing.item, { action: "ignore" })} /></Modal> : null}
    </AuthenticatedPageFrame>
  );
}
