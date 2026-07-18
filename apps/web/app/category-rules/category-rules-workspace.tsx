"use client";

import type { CategoryRuleCondition, CategoryRulesView, CategoryRuleView } from "@clearpath/validation";
import { ChevronDown, Plus, RefreshCw, Settings2, Tags, Trash2, X } from "lucide-react";
import { FormEvent, useCallback, useEffect, useState } from "react";

import { AuthenticatedShell } from "../authenticated-shell";
import styles from "./category-rules.module.css";

export type RulePrefill = { field: string; operator: string; value: string; categoryId: number | null };

const fieldLabels: Record<string, string> = { description: "Description", account: "Account", amount: "Amount", category: "Current Category" };
const operatorLabels: Record<string, string> = { contains: "Contains", equals: "Equals", starts_with: "Starts With", ends_with: "Ends With", not_contains: "Does Not Contain", gt: "Greater Than", gte: "Greater Than Or Equal To", lt: "Less Than", lte: "Less Than Or Equal To", between: "Between" };

function condition(field = "description", operator = "contains", value = ""): CategoryRuleCondition {
  return { field: field as CategoryRuleCondition["field"], operator: operator as CategoryRuleCondition["operator"], value, valueSecondary: "", group: "primary", join: "and" };
}

async function responseMessage(response: Response, fallback: string) {
  const payload = await response.json().catch(() => null) as { message?: string } | null;
  return payload?.message || fallback;
}

function appliedMessage(prefix: string, count: number) {
  return `${prefix} and applied to ${count} existing transaction${count === 1 ? "" : "s"}.`;
}

export function CategoryRulesWorkspace({ prefill }: { prefill: RulePrefill }) {
  const [data, setData] = useState<CategoryRulesView | null>(null);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const [managerOpen, setManagerOpen] = useState(false);

  const load = useCallback(async () => {
    const response = await fetch("/api/category-rules", { cache: "no-store" });
    if (!response.ok) { setError(await responseMessage(response, "We could not load categorization rules.")); return; }
    setData(await response.json() as CategoryRulesView);
    setError("");
  }, []);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    if (!managerOpen) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = previousOverflow; };
  }, [managerOpen]);

  const canEdit = Boolean(data && (data.session.primaryAccountHolder || data.session.subject.householdRole !== "viewer"));

  const mutate = async (url: string, options: RequestInit, success: string | ((payload: Record<string, unknown>) => string)) => {
    setBusy(true); setError(""); setStatus("");
    const response = await fetch(url, { ...options, headers: { "content-type": "application/json", ...options.headers } }).catch(() => null);
    if (!response) { setError("ClearPath is temporarily unavailable. Please try again."); setBusy(false); return null; }
    if (!response.ok) { setError(await responseMessage(response, "We could not save that change.")); setBusy(false); return null; }
    const payload = await response.json().catch(() => ({})) as Record<string, unknown>;
    setStatus(typeof success === "function" ? success(payload) : success);
    await load();
    setBusy(false);
    return payload;
  };

  const createRule = async (categoryId: number, conditions: CategoryRuleCondition[]) => Boolean(await mutate(
    "/api/category-rules",
    { method: "POST", body: JSON.stringify({ categoryId, conditions }) },
    (payload) => appliedMessage("Rule created", Number(payload.appliedCount ?? 0)),
  ));

  const createCategory = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const saved = await mutate("/api/categories", { method: "POST", body: JSON.stringify({ name: form.get("name"), kind: form.get("kind"), activateBudget: false }) }, "Category added.");
    if (saved) formElement.reset();
  };

  const content = <main className={styles.page}>
    <header className={styles.pageHeader}>
      <div><p className={styles.eyebrow}>Transaction Review</p><h1>Categorization Rules</h1><p>Teach ClearPath how to categorize repeat merchants so future transactions need less cleanup.</p></div>
      <button type="button" className={styles.secondaryButton} disabled={!canEdit} onClick={() => setManagerOpen(true)}><Settings2 size={16} aria-hidden="true" />Manage Categories</button>
    </header>

    {error ? <div className={styles.error} role="alert">{error}</div> : null}
    {status ? <div className={styles.status} role="status">{status}</div> : null}
    {data && !canEdit ? <div className={styles.viewerNotice}>Shared viewer access is read-only.</div> : null}

    {!data ? <div className={styles.loading}><RefreshCw size={20} className={styles.spin} />Loading categorization rules...</div> : <>
      <div className={styles.introGrid}>
        <section className={styles.createSection} aria-labelledby="create-rule-title">
          <div className={styles.sectionHeading}><div><h2 id="create-rule-title">Create A Rule</h2><p>Match transaction details and apply one category.</p></div><Tags size={21} aria-hidden="true" /></div>
          <RuleBuilder
            initialConditions={[condition(prefill.field, prefill.operator, prefill.value)]}
            initialCategoryId={data.categories.some((category) => category.id === prefill.categoryId) ? prefill.categoryId : null}
            categories={data.categories}
            canEdit={canEdit}
            busy={busy}
            submitLabel="Save Rule"
            resetAfterSave
            onManageCategories={() => setManagerOpen(true)}
            onSubmit={createRule}
          />
        </section>
        <aside className={styles.education} aria-labelledby="how-rules-work-title">
          <h2 id="how-rules-work-title">How Rules Work</h2>
          <p>Use Categorization Rules for transactions that show up the same way over and over, like payroll, groceries, utilities, subscriptions, or credit card payments.</p>
          <p>A rule watches for matching details such as merchant name, account, amount, or current category. When a future import matches, ClearPath applies the category automatically.</p>
          <div><strong>Example</strong><span>If the description contains Kroger, apply Groceries. Keep rules specific when a merchant could belong to more than one category.</span></div>
        </aside>
      </div>

      <section className={styles.savedSection} aria-labelledby="saved-rules-title">
        <div className={styles.savedHeader}><div><h2 id="saved-rules-title">Saved Rules</h2><p>{data.rules.length} Total</p></div></div>
        {data.rules.length ? <div className={styles.rulesStack}>{data.rules.map((rule) => <SavedRule key={rule.id} rule={rule} data={data} canEdit={canEdit} busy={busy} onManageCategories={() => setManagerOpen(true)} onMutate={mutate} />)}</div> : <div className={styles.empty}><Tags size={22} /><strong>No Rules Yet</strong><span>Create your first rule after you notice a merchant you categorize the same way every time.</span></div>}
      </section>

      {managerOpen ? <div className={styles.modalBackdrop} role="presentation" onMouseDown={(event) => { if (event.currentTarget === event.target) setManagerOpen(false); }}>
        <section className={styles.modal} role="dialog" aria-modal="true" aria-labelledby="category-manager-title">
          <div className={styles.modalHeader}><div><h2 id="category-manager-title">Manage Categories</h2><p>Changes apply across transactions and planning worksheets.</p></div><button type="button" className={styles.iconButton} title="Close" aria-label="Close category manager" onClick={() => setManagerOpen(false)}><X size={19} /></button></div>
          <form className={styles.categoryCreate} onSubmit={createCategory}><label>Name<input name="name" maxLength={80} required disabled={!canEdit} /></label><label>Type<select name="kind" defaultValue="expense" disabled={!canEdit}><option value="expense">Expense</option><option value="income">Income</option></select></label><button type="submit" className={styles.primaryButton} disabled={!canEdit || busy}><Plus size={16} />Add Category</button></form>
          <div className={styles.categoryList}>{data.categories.filter((category) => category.canManage).map((category) => <CategoryManagerRow key={category.id} category={category} categories={data.categories} canEdit={canEdit} busy={busy} onMutate={mutate} />)}</div>
        </section>
      </div> : null}
    </>}
  </main>;

  return data ? <AuthenticatedShell session={data.session}>{content}</AuthenticatedShell> : content;
}

function RuleBuilder({ initialConditions, initialCategoryId, categories, canEdit, busy, submitLabel, resetAfterSave = false, onManageCategories, onSubmit }: {
  initialConditions: CategoryRuleCondition[];
  initialCategoryId: number | null;
  categories: CategoryRulesView["categories"];
  canEdit: boolean;
  busy: boolean;
  submitLabel: string;
  resetAfterSave?: boolean;
  onManageCategories(): void;
  onSubmit(categoryId: number, conditions: CategoryRuleCondition[]): Promise<boolean>;
}) {
  const [conditions, setConditions] = useState(initialConditions.length ? initialConditions : [condition()]);
  const [categoryId, setCategoryId] = useState(initialCategoryId ? String(initialCategoryId) : "");

  const update = (index: number, changes: Partial<CategoryRuleCondition>) => setConditions((rows) => rows.map((row, rowIndex) => rowIndex === index ? { ...row, ...changes } : row));
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!categoryId) return;
    const saved = await onSubmit(Number(categoryId), conditions);
    if (saved && resetAfterSave) { setConditions([condition()]); setCategoryId(""); }
  };

  return <form className={styles.ruleForm} onSubmit={submit}>
    <div className={styles.conditionList}>{conditions.map((row, index) => <div className={`${styles.conditionRow} ${row.operator === "between" ? styles.betweenRow : ""}`} key={index}>
      {index ? <label>Join<select aria-label={`Condition ${index + 1} join`} value={row.join} disabled={!canEdit || busy} onChange={(event) => update(index, { join: event.target.value as "and" | "or" })}><option value="and">AND</option><option value="or">OR</option></select></label> : <span className={styles.whenLabel}>When</span>}
      <label>Field<select aria-label={`Condition ${index + 1} field`} value={row.field} disabled={!canEdit || busy} onChange={(event) => update(index, { field: event.target.value as CategoryRuleCondition["field"] })}>{Object.entries(fieldLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      <label>Operator<select aria-label={`Condition ${index + 1} operator`} value={row.operator} disabled={!canEdit || busy} onChange={(event) => update(index, { operator: event.target.value as CategoryRuleCondition["operator"] })}>{Object.entries(operatorLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      <label>Value<input aria-label={`Condition ${index + 1} value`} value={row.value} disabled={!canEdit || busy} placeholder={index ? "Optional condition" : "e.g., Kroger"} required onChange={(event) => update(index, { value: event.target.value })} /></label>
      {row.operator === "between" ? <label>Upper Limit<input aria-label={`Condition ${index + 1} upper limit`} value={row.valueSecondary} disabled={!canEdit || busy} required onChange={(event) => update(index, { valueSecondary: event.target.value })} /></label> : null}
      {index ? <button type="button" className={styles.iconButton} title="Remove condition" aria-label={`Remove condition ${index + 1}`} disabled={!canEdit || busy} onClick={() => setConditions((rows) => rows.filter((_, rowIndex) => rowIndex !== index))}><Trash2 size={16} /></button> : null}
    </div>)}</div>
    <button type="button" className={styles.secondaryButton} disabled={!canEdit || busy || conditions.length >= 4} onClick={() => setConditions((rows) => [...rows, condition()])}><Plus size={15} />Add Condition</button>
    <div className={styles.categoryChoice}><label>Apply Category<select value={categoryId} disabled={!canEdit || busy} required onChange={(event) => setCategoryId(event.target.value)}><option value="">Select A Category</option>{categories.map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}</select></label><button type="button" className={styles.textButton} disabled={!canEdit} onClick={onManageCategories}>Manage Categories</button></div>
    <button type="submit" className={styles.primaryButton} disabled={!canEdit || busy || !categoryId}>{submitLabel}</button>
  </form>;
}

function SavedRule({ rule, data, canEdit, busy, onManageCategories, onMutate }: { rule: CategoryRuleView; data: CategoryRulesView; canEdit: boolean; busy: boolean; onManageCategories(): void; onMutate: (url: string, options: RequestInit, success: string | ((payload: Record<string, unknown>) => string)) => Promise<Record<string, unknown> | null> }) {
  const first = rule.conditions[0];
  const summary = first ? `${fieldLabels[first.field]} ${operatorLabels[first.operator]} "${first.value}"${first.operator === "between" && first.valueSecondary ? ` and "${first.valueSecondary}"` : ""}` : rule.summary;
  return <details className={styles.ruleCard}>
    <summary><div><strong>{summary}</strong>{rule.conditions.length > 1 ? <span>+ {rule.conditions.length - 1} More</span> : null}<small>{rule.category.name}</small></div><span>Edit <ChevronDown size={15} /></span></summary>
    <div className={styles.ruleEditor}><div className={styles.ruleSummary}><span>{rule.ruleLogic === "custom" ? "Custom Conditions" : "All Conditions"}</span><p>{rule.summary}</p></div>
      <RuleBuilder initialConditions={rule.conditions} initialCategoryId={rule.category.id} categories={data.categories} canEdit={canEdit} busy={busy} submitLabel="Save Changes" onManageCategories={onManageCategories} onSubmit={async (categoryId, conditions) => Boolean(await onMutate(`/api/category-rules/${rule.id}`, { method: "PATCH", body: JSON.stringify({ categoryId, conditions }) }, (payload) => appliedMessage("Rule updated", Number(payload.appliedCount ?? 0))))} />
      <button type="button" className={styles.dangerButton} disabled={!canEdit || busy} onClick={() => window.confirm("Delete this rule?") && void onMutate(`/api/category-rules/${rule.id}`, { method: "DELETE", body: JSON.stringify({ confirm: true }) }, "Rule deleted.")}><Trash2 size={15} />Delete Rule</button>
    </div>
  </details>;
}

function CategoryManagerRow({ category, categories, canEdit, busy, onMutate }: { category: CategoryRulesView["categories"][number]; categories: CategoryRulesView["categories"]; canEdit: boolean; busy: boolean; onMutate: (url: string, options: RequestInit, success: string) => Promise<Record<string, unknown> | null> }) {
  const [name, setName] = useState(category.name);
  const [kind, setKind] = useState(category.kind);
  const [replacement, setReplacement] = useState("");
  return <div className={styles.categoryRow}><label>Name<input aria-label={`${category.name} name`} value={name} disabled={!canEdit} onChange={(event) => setName(event.target.value)} /></label><label>Type<select aria-label={`${category.name} type`} value={kind} disabled={!canEdit} onChange={(event) => setKind(event.target.value)}><option value="expense">Expense</option><option value="income">Income</option></select></label><button type="button" className={styles.secondaryButton} disabled={!canEdit || busy || !name.trim()} onClick={() => void onMutate(`/api/categories/${category.id}`, { method: "PATCH", body: JSON.stringify({ name, kind }) }, "Category updated.")}>Save</button><label>Move Transactions<select aria-label={`${category.name} replacement`} value={replacement} disabled={!canEdit} onChange={(event) => setReplacement(event.target.value)}><option value="">Uncategorized</option>{categories.filter((row) => row.id !== category.id).map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label><button type="button" className={styles.dangerButton} disabled={!canEdit || busy} onClick={() => window.confirm(`Delete ${category.name}?`) && void onMutate(`/api/categories/${category.id}`, { method: "DELETE", body: JSON.stringify({ replacementCategoryId: replacement ? Number(replacement) : null }) }, "Category removed.")}><Trash2 size={15} />Delete</button></div>;
}
