"use client";

import type { TransactionReviewView, TransactionView } from "@clearpath/validation";
import { CircleDollarSign, Landmark, Loader2, Plus, ReceiptText, Repeat2, Scissors, Tags, Trash2 } from "lucide-react";
import Link from "next/link";
import { FormEvent, useMemo, useState } from "react";

import styles from "./transactions.module.css";

type Category = TransactionReviewView["categories"][number];
type BudgetAction = TransactionReviewView["budgetActions"][string] | undefined;
type AmortizationAction = TransactionReviewView["amortizationActions"][string] | undefined;
type Mutate = (url: string, options: RequestInit, message: string, redirect?: string) => Promise<Record<string, unknown> | null>;

const cadenceOptions = { weekly: "Weekly", biweekly: "Every Two Weeks", semimonthly: "Twice Per Month", monthly: "Monthly", quarterly: "Quarterly", annual: "Annual" };
const weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const weekNumbers = ["First", "Second", "Third", "Fourth", "Last"];

function currency(amount: number) {
  return Math.abs(amount).toLocaleString(undefined, { style: "currency", currency: "USD" });
}

function dateLabel(value: string) {
  return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", year: "numeric" }).format(new Date(`${value}T12:00:00`));
}

export function TransactionRow({ transaction, categories, budgetAction, amortizationAction, recurring, canEdit, busy, onMutate }: { transaction: TransactionView; categories: Category[]; budgetAction?: BudgetAction; amortizationAction?: AmortizationAction; recurring: boolean; canEdit: boolean; busy: boolean; onMutate: Mutate }) {
  const [expanded, setExpanded] = useState(false);
  const expenseCategories = categories.filter((category) => category.kind !== "income");
  const detailBits = [transaction.plaidCategoryLabel, transaction.paymentChannelLabel, transaction.locationSummary].filter(Boolean);
  return <article id={`transaction-${transaction.id}`} className={styles.transactionRow}>
    <div className={styles.dateCell}><strong>{dateLabel(transaction.postedDate)}</strong>{transaction.pending ? <span className={styles.pendingBadge}>Pending</span> : null}</div>
    <div className={styles.descriptionCell}><div className={styles.merchantLine}><strong>{transaction.displayMerchant}</strong>{recurring ? <span className={styles.recurringBadge}><Repeat2 size={12} />Recurring</span> : null}</div>{transaction.rawDescription ? <span>{transaction.rawDescription}</span> : null}<small>{transaction.account?.name || transaction.sourceName || "Imported"}{detailBits.length ? ` · ${detailBits.join(" · ")}` : ""}</small>{transaction.splits.length ? <span className={styles.splitBadge}>{transaction.splits.length} split lines</span> : null}</div>
    <div className={styles.categoryCell}><CategoryControl transaction={transaction} categories={categories} recurring={recurring} canEdit={canEdit} busy={busy} onMutate={onMutate} /></div>
    <div className={`${styles.amountCell} ${transaction.amount > 0 ? styles.income : styles.expense}`}><strong>{transaction.amount > 0 ? "+" : "-"}{currency(transaction.amount)}</strong><button type="button" className={styles.detailButton} onClick={() => setExpanded((value) => !value)} aria-expanded={expanded} aria-controls={`transaction-details-${transaction.id}`}>{expanded ? "Close" : "Details"}</button></div>
    {expanded ? <div id={`transaction-details-${transaction.id}`} className={styles.transactionDetails}>
      <div className={styles.actionStrip}>
        <Link className={styles.textButton} href={`/category-rules?condition_value=${encodeURIComponent(transaction.displayMerchant)}${transaction.category ? `&category_id=${transaction.category.id}` : ""}`}><Tags size={15} />Create Rule</Link>
        {budgetAction ? <button type="button" className={styles.textButton} disabled={!canEdit || busy} title={budgetAction.hint} onClick={() => void onMutate(`/api/transactions/${transaction.id}/budget-category`, { method: "POST", body: "{}" }, `${budgetAction.categoryName} budget created.`)}><CircleDollarSign size={15} />Create Budget · {budgetAction.targetLabel}</button> : null}
        {amortizationAction ? <button type="button" className={styles.textButton} disabled={!canEdit || busy} title={amortizationAction.hint || ""} onClick={() => void onMutate(`/api/transactions/${transaction.id}/loan-plan`, { method: "POST", body: "{}" }, "Loan plan ready.", "/loan-plans/:id")}><Landmark size={15} />{amortizationAction.label}</button> : null}
      </div>
      <div className={styles.detailGrid}><SplitEditor transaction={transaction} categories={expenseCategories} canEdit={canEdit} busy={busy} onMutate={onMutate} /><div className={styles.sourceDetail}><h3><ReceiptText size={16} />Source Detail</h3><dl><div><dt>Posted</dt><dd>{transaction.postedDate}</dd></div><div><dt>Account</dt><dd>{transaction.account?.name || transaction.sourceName || "Imported"}</dd></div><div><dt>Channel</dt><dd>{transaction.paymentChannelLabel || "Not provided"}</dd></div><div><dt>Location</dt><dd>{transaction.locationSummary || "Not provided"}</dd></div>{transaction.notes ? <div><dt>Notes</dt><dd>{transaction.notes}</dd></div> : null}</dl></div></div>
    </div> : null}
  </article>;
}

function CategoryControl({ transaction, categories, recurring, canEdit, busy, onMutate }: { transaction: TransactionView; categories: Category[]; recurring: boolean; canEdit: boolean; busy: boolean; onMutate: Mutate }) {
  const [categoryId, setCategoryId] = useState(transaction.category ? String(transaction.category.id) : "");
  const [newCategory, setNewCategory] = useState("");
  const [applySimilar, setApplySimilar] = useState(true);
  const [recurringName, setRecurringName] = useState(transaction.displayMerchant);
  const [frequency, setFrequency] = useState<keyof typeof cadenceOptions>("monthly");
  const [startDate, setStartDate] = useState(transaction.postedDate);
  const [secondDate, setSecondDate] = useState("");
  const [selectedDays, setSelectedDays] = useState<number[]>([new Date(`${transaction.postedDate}T12:00:00`).getDay() === 0 ? 6 : new Date(`${transaction.postedDate}T12:00:00`).getDay() - 1]);
  const [monthlyWeekday, setMonthlyWeekday] = useState<number | null>(null);
  const [monthlyWeeks, setMonthlyWeeks] = useState<number[]>([]);

  const saveCategory = async (nextId: string, nextName = "") => {
    const result = await onMutate(`/api/transactions/${transaction.id}/category`, { method: "PATCH", body: JSON.stringify({ categoryId: nextId ? Number(nextId) : null, newCategoryName: nextName || null, applyToSimilar: applySimilar }) }, "Transaction category updated.");
    if (result && nextName) setNewCategory("");
  };

  const recurringSubmit = (event: FormEvent) => {
    event.preventDefault();
    void onMutate(`/api/transactions/${transaction.id}/category`, { method: "PATCH", body: JSON.stringify({
      categoryId: categoryId ? Number(categoryId) : null, newCategoryName: null, applyToSimilar: applySimilar, markRecurring: true,
      recurringName, recurringStartDate: startDate, recurringSecondDate: secondDate || null, recurringFrequency: frequency,
      recurringDaysOfWeek: selectedDays, recurringMonthlyWeekNumbers: monthlyWeeks, recurringMonthlyWeekday: monthlyWeekday,
    }) }, recurring ? "Recurring expense updated." : "Recurring expense saved.");
  };

  return <div className={styles.categoryControl}>
    <label className={styles.visuallyHidden} htmlFor={`category-${transaction.id}`}>Category for {transaction.displayMerchant}</label>
    {busy ? <span className={styles.savingBadge} role="status"><Loader2 size={13} className={styles.spin} aria-hidden="true" />Saving</span> : null}
    <select id={`category-${transaction.id}`} value={categoryId} disabled={!canEdit || busy} onChange={(event) => { const value = event.target.value; setCategoryId(value); if (value) void saveCategory(value); }}><option value="">Uncategorized</option>{categories.map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}</select>
    {canEdit ? <label className={styles.compactCheck}><input type="checkbox" checked={applySimilar} onChange={(event) => setApplySimilar(event.target.checked)} />Apply to similar</label> : null}
    {canEdit ? <details className={styles.inlineDetails}><summary>New category</summary><div className={styles.inlineCreate}><input aria-label={`New category for ${transaction.displayMerchant}`} value={newCategory} maxLength={80} onChange={(event) => setNewCategory(event.target.value)} /><button type="button" title="Add category" disabled={!newCategory.trim() || busy} onClick={() => void saveCategory("", newCategory)}><Plus size={15} /></button></div></details> : null}
    {canEdit ? <details className={styles.inlineDetails}><summary>{recurring ? "Edit recurring" : "Mark recurring"}</summary><form className={styles.recurringForm} onSubmit={recurringSubmit}><label>Name<input value={recurringName} onChange={(event) => setRecurringName(event.target.value)} required /></label><label>Cadence<select value={frequency} onChange={(event) => setFrequency(event.target.value as keyof typeof cadenceOptions)}>{Object.entries(cadenceOptions).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><label>First Expected Date<input type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} required /></label>{frequency === "semimonthly" ? <label>Second Date<input type="date" value={secondDate} onChange={(event) => setSecondDate(event.target.value)} /></label> : null}{frequency === "weekly" || frequency === "biweekly" ? <fieldset><legend>Days Of Week</legend>{weekdays.map((day, index) => <label key={day}><input type="checkbox" checked={selectedDays.includes(index)} onChange={() => setSelectedDays((current) => current.includes(index) ? current.filter((value) => value !== index) : [...current, index])} />{day.slice(0, 3)}</label>)}</fieldset> : null}{frequency === "monthly" || frequency === "semimonthly" ? <><label>Weekday Pattern<select value={monthlyWeekday ?? ""} onChange={(event) => setMonthlyWeekday(event.target.value === "" ? null : Number(event.target.value))}><option value="">Day of month</option>{weekdays.map((day, index) => <option key={day} value={index}>{day}</option>)}</select></label><fieldset><legend>Weeks In Month</legend>{weekNumbers.map((week, index) => <label key={week}><input type="checkbox" checked={monthlyWeeks.includes(index + 1)} onChange={() => setMonthlyWeeks((current) => current.includes(index + 1) ? current.filter((value) => value !== index + 1) : [...current, index + 1])} />{week}</label>)}</fieldset></> : null}<button type="submit" className={styles.secondaryButton} disabled={busy || !categoryId}>{recurring ? "Update Recurring Expense" : "Save Recurring Expense"}</button></form></details> : null}
  </div>;
}

type SplitLine = { categoryId: string; amount: string; notes: string };

function SplitEditor({ transaction, categories, canEdit, busy, onMutate }: { transaction: TransactionView; categories: Category[]; canEdit: boolean; busy: boolean; onMutate: Mutate }) {
  const initialLines = useMemo<SplitLine[]>(() => transaction.splits.length ? transaction.splits.map((split) => ({ categoryId: String(split.category.id), amount: split.amount.toFixed(2), notes: split.notes || "" })) : [{ categoryId: transaction.category ? String(transaction.category.id) : "", amount: Math.abs(transaction.amount).toFixed(2), notes: "" }, { categoryId: "", amount: "", notes: "" }], [transaction]);
  const [lines, setLines] = useState(initialLines);
  const target = Math.abs(transaction.amount);
  const total = lines.reduce((sum, line) => sum + (Number(line.amount) || 0), 0);
  const valid = lines.filter((line) => line.categoryId && Number(line.amount) > 0).length >= 2 && Math.abs(total - target) < .005;
  const update = (index: number, key: keyof SplitLine, value: string) => setLines((current) => current.map((line, lineIndex) => lineIndex === index ? { ...line, [key]: value } : line));

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!valid) return;
    void onMutate(`/api/transactions/${transaction.id}/splits`, { method: "PATCH", body: JSON.stringify({ clearSplits: false, splits: lines.filter((line) => line.categoryId && Number(line.amount) > 0).map((line) => ({ categoryId: Number(line.categoryId), amount: Number(line.amount), notes: line.notes || null })) }) }, "Transaction split saved.");
  };

  return <details className={styles.splitEditor}><summary><Scissors size={16} />Split Transaction</summary><form onSubmit={submit}><div className={styles.splitTotal}><strong>{currency(total)} of {currency(target)}</strong><span className={valid ? styles.valid : styles.invalid}>{valid ? "Ready to save" : "Split lines must equal the transaction total"}</span></div>{lines.map((line, index) => <div className={styles.splitLine} key={index}><select aria-label={`Split ${index + 1} category`} value={line.categoryId} onChange={(event) => update(index, "categoryId", event.target.value)} disabled={!canEdit}><option value="">Choose category</option>{categories.map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}</select><input aria-label={`Split ${index + 1} amount`} inputMode="decimal" value={line.amount} onChange={(event) => update(index, "amount", event.target.value)} disabled={!canEdit} /><input aria-label={`Split ${index + 1} notes`} placeholder="Notes" value={line.notes} onChange={(event) => update(index, "notes", event.target.value)} disabled={!canEdit} /><button type="button" className={styles.iconButton} title="Remove split line" disabled={!canEdit || lines.length <= 2} onClick={() => setLines((current) => current.filter((_, lineIndex) => lineIndex !== index))}><Trash2 size={15} /></button></div>)}<div className={styles.splitActions}><button type="button" className={styles.secondaryButton} disabled={!canEdit} onClick={() => setLines((current) => [...current, { categoryId: "", amount: "", notes: "" }])}><Plus size={15} />Add Line</button><button type="submit" className={styles.primaryButton} disabled={!canEdit || busy || !valid}>Save Split</button>{transaction.splits.length ? <button type="button" className={styles.ghostButton} disabled={!canEdit || busy} onClick={() => void onMutate(`/api/transactions/${transaction.id}/splits`, { method: "PATCH", body: JSON.stringify({ clearSplits: true, splits: [] }) }, "Transaction split cleared.")}>Clear Split</button> : null}</div></form></details>;
}
