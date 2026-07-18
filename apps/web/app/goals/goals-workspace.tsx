"use client";

import { goalMutationInputSchema, goalsViewSchema, type GoalMutationInput, type GoalsView, type GoalView } from "@clearpath/validation";
import { Pencil, Plus, RefreshCw, Target, Trash2, X } from "lucide-react";
import Link from "next/link";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import { AuthenticatedShell } from "../authenticated-shell";
import styles from "./goals.module.css";

const currency = (value: number) => new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(value);
const dateLabel = (value: string) => new Date(`${value}T12:00:00`).toLocaleDateString("en-US");

async function responseMessage(response: Response, fallback: string) {
  const body = await response.json().catch(() => null) as { message?: string } | null;
  return body?.message || fallback;
}

function numberOrNull(value: FormDataEntryValue | null) {
  const raw = String(value ?? "").replaceAll(",", "").trim();
  if (!raw) return null;
  const parsed = Number(raw);
  return Number.isFinite(parsed) ? parsed : null;
}

function formValue(form: HTMLFormElement): GoalMutationInput | null {
  const values = new FormData(form);
  const goalType = String(values.get("goal_type") ?? "savings");
  const parsed = goalMutationInputSchema.safeParse({
    name: values.get("name"),
    goalType,
    targetAmount: numberOrNull(values.get("target_amount")),
    currentAmount: numberOrNull(values.get("current_amount")),
    monthlyContribution: numberOrNull(values.get("monthly_contribution")),
    targetDate: String(values.get("target_date") ?? "").trim() || null,
    fixedExpenseItemId: goalType === "debt" ? numberOrNull(values.get("fixed_expense_item_id")) : null,
  });
  return parsed.success ? parsed.data : null;
}

export function GoalsWorkspace() {
  const [data, setData] = useState<GoalsView | null>(null);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const [editGoal, setEditGoal] = useState<GoalView | null>(null);

  const load = useCallback(async () => {
    setError("");
    try {
      const response = await fetch("/api/goals", { cache: "no-store" });
      if (!response.ok) throw new Error(await responseMessage(response, "We could not load goals."));
      const parsed = goalsViewSchema.safeParse(await response.json());
      if (!parsed.success) throw new Error("Goal data did not match the expected contract.");
      setData(parsed.data);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "We could not load goals.");
    }
  }, []);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    if (!editGoal) return;
    document.body.style.overflow = "hidden";
    const close = (event: KeyboardEvent) => { if (event.key === "Escape") setEditGoal(null); };
    document.addEventListener("keydown", close);
    return () => { document.body.style.overflow = ""; document.removeEventListener("keydown", close); };
  }, [editGoal]);

  const canEdit = Boolean(data && (data.session.primaryAccountHolder || data.session.subject.householdRole !== "viewer"));
  const upgrade = useMemo(() => {
    if (!data) return null;
    const loan = data.session.featureAccess.find((row) => row.feature === "mortgage_loan_planning");
    const retirement = data.session.featureAccess.find((row) => row.feature === "retirement_planning");
    if (loan && !loan.enabled && !loan.hidden) return { label: loan.requiredPlan, copy: `${loan.requiredPlan} adds Mortgage/Loan Planning so debt payoff goals can use richer amortization schedules.` };
    if (retirement && !retirement.enabled && !retirement.hidden) return { label: "Premier", copy: "Premier adds Retirement Planning education and AI-guided dashboard focus for bigger long-term questions." };
    return null;
  }, [data]);

  const mutate = async (url: string, method: "POST" | "PATCH" | "DELETE", payload: GoalMutationInput | null, success: string) => {
    setBusy(true); setError(""); setStatus("");
    try {
      const response = await fetch(url, { method, headers: { "content-type": "application/json" }, body: payload ? JSON.stringify(payload) : undefined });
      if (!response.ok) throw new Error(await responseMessage(response, "That goal change could not be saved."));
      setStatus(success); setEditGoal(null); await load(); return true;
    } catch (mutationError) {
      setError(mutationError instanceof Error ? mutationError.message : "That goal change could not be saved."); return false;
    } finally { setBusy(false); }
  };

  const create = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = event.currentTarget;
    const payload = formValue(form);
    if (!payload) { setError("Check the goal details."); return; }
    if (await mutate("/api/goals", "POST", payload, "Goal created.")) form.reset();
  };

  const update = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!editGoal) return;
    const payload = formValue(event.currentTarget);
    if (!payload) { setError("Check the goal details."); return; }
    await mutate(`/api/goals/${editGoal.id}`, "PATCH", payload, "Goal updated.");
  };

  const remove = async (goal: GoalView) => {
    if (!window.confirm(`Delete ${goal.name}?`)) return;
    await mutate(`/api/goals/${goal.id}`, "DELETE", null, "Goal deleted.");
  };

  const content = <main className={styles.page}>
    <header className={styles.pageHeader}><div><p className={styles.eyebrow}>Long-Term Progress</p><h1>Goals</h1><p>Track what you&apos;re saving toward and paying off.</p></div></header>
    <div className={styles.content}>
      {error ? <div className={styles.error} role="alert">{error}</div> : null}
      {status ? <div className={styles.status} role="status">{status}</div> : null}
      {data && !canEdit ? <div className={styles.viewerNotice}>Shared viewer access is read-only.</div> : null}
      {upgrade ? <section className={styles.upgrade}><div><h2>Connect goals to longer-range planning.</h2><p>{upgrade.copy}</p></div><Link href="/select-plan">Upgrade To {upgrade.label}</Link></section> : null}
      {!data ? <div className={styles.loading}><RefreshCw className={styles.spin} size={20} />Loading goals...</div> : <>
        <section className={styles.topGrid}>
          <div className={styles.panel}><header><h2>Create A Goal</h2></header><div className={styles.formBody}><GoalForm loanOptions={data.loanOptions} canEdit={canEdit} busy={busy} onSubmit={create} submitLabel="Add Goal" /></div></div>
          <div className={styles.panel}><header><h2>How Goals Work</h2></header><div className={styles.education}><Target size={26} /><p>Budgets are monthly targets. Goals are longer-term outcomes, and their monthly contribution can flow back into this month&apos;s plan.</p><p>Savings goals can use a contribution or target date. Debt goals can follow a tracked mortgage or loan and estimate extra principal needed for a payoff date.</p></div></div>
        </section>
        <section className={styles.goalSection} aria-labelledby="goal-list-title"><div className={styles.sectionHeading}><h2 id="goal-list-title">Your Goals</h2><span>{data.goals.length}</span></div>
          {data.goals.length ? <div className={styles.goalGrid}>{data.goals.map((goal) => <GoalCard key={goal.id} goal={goal} canEdit={canEdit} busy={busy} onEdit={() => setEditGoal(goal)} onDelete={() => void remove(goal)} />)}</div> : <div className={styles.empty}><Target size={28} /><strong>No Goals Yet</strong><p>Create a savings goal or debt paydown target to track your progress.</p></div>}
        </section>
      </>}
    </div>
    {editGoal && data ? <div className={styles.modal} role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setEditGoal(null); }}><section role="dialog" aria-modal="true" aria-labelledby="edit-goal-title"><header><div><h2 id="edit-goal-title">Edit Goal</h2><p>{editGoal.name}</p></div><button type="button" aria-label="Close Edit Goal" title="Close" onClick={() => setEditGoal(null)}><X size={18} /></button></header><div className={styles.formBody}><GoalForm goal={editGoal} loanOptions={data.loanOptions} canEdit={canEdit} busy={busy} onSubmit={update} submitLabel="Save Goal" /></div></section></div> : null}
  </main>;

  return data ? <AuthenticatedShell session={data.session}>{content}</AuthenticatedShell> : content;
}

function GoalForm({ goal, loanOptions, canEdit, busy, onSubmit, submitLabel }: { goal?: GoalView; loanOptions: GoalsView["loanOptions"]; canEdit: boolean; busy: boolean; onSubmit(event: FormEvent<HTMLFormElement>): void; submitLabel: string }) {
  const [type, setType] = useState(goal?.goalType ?? "savings");
  return <form className={styles.goalForm} onSubmit={onSubmit}>
    <div className={styles.inputGrid}><label>Goal Name<input name="name" defaultValue={goal?.name ?? ""} placeholder="Emergency fund" required disabled={!canEdit} /></label><label>Goal Type<select name="goal_type" value={type} disabled={!canEdit} onChange={(event) => setType(event.target.value as "savings" | "debt")}><option value="savings">Savings</option><option value="debt">Debt Paydown</option></select></label></div>
    {type === "debt" ? <label>Debt This Goal Applies To<select aria-label="Debt This Goal Applies To" name="fixed_expense_item_id" defaultValue={goal?.fixedExpenseItemId ?? ""} disabled={!canEdit}><option value="">Unlinked Debt Goal</option>{loanOptions.map((loan) => <option key={loan.fixedExpenseItemId} value={loan.fixedExpenseItemId}>{loan.name} - {loan.loanKind === "mortgage" ? "Mortgage" : "Loan"} ({currency(loan.currentBalance)} Balance)</option>)}</select><small>Choose a tracked mortgage or loan so this goal follows that balance.</small></label> : null}
    <div className={styles.amountGrid}><label>Target Amount<input name="target_amount" inputMode="decimal" defaultValue={goal?.targetAmount ?? ""} disabled={!canEdit} /></label><label>Current Amount<input name="current_amount" inputMode="decimal" defaultValue={goal?.currentAmount ?? 0} disabled={!canEdit} /></label><label>Monthly Contribution<input name="monthly_contribution" inputMode="decimal" defaultValue={goal?.monthlyContribution ?? 0} disabled={!canEdit} /></label></div>
    <label>Target Date<input type="date" name="target_date" defaultValue={goal?.targetDate ?? ""} disabled={!canEdit} /><small>Optional. ClearPath will estimate the monthly amount needed to reach it.</small></label>
    <button type="submit" className={styles.primaryButton} disabled={!canEdit || busy}><Plus size={16} />{submitLabel}</button>
  </form>;
}

function GoalCard({ goal, canEdit, busy, onEdit, onDelete }: { goal: GoalView; canEdit: boolean; busy: boolean; onEdit(): void; onDelete(): void }) {
  const progress = Math.min(Math.max(goal.progress, 0), 100);
  return <article className={styles.goalCard}>
    <header><div><span>{goal.goalType === "savings" ? "Savings" : "Debt Paydown"}</span><h3>{goal.name}</h3></div><div><button type="button" aria-label={`Edit ${goal.name}`} title="Edit" disabled={!canEdit || busy} onClick={onEdit}><Pencil size={16} /></button><button type="button" aria-label={`Delete ${goal.name}`} title="Delete" disabled={!canEdit || busy} onClick={onDelete}><Trash2 size={16} /></button></div></header>
    <div className={styles.goalAmounts}><strong>{currency(goal.currentAmount)}</strong><span>of {currency(goal.targetAmount)}</span></div>
    <div className={styles.progress}><i className={progress >= 100 ? styles.complete : ""} style={{ width: `${progress}%` }} /></div>
    <div className={styles.progressMeta}><span>{Math.round(goal.progress)}% Complete</span><span>{currency(goal.remaining)} To Go</span></div>
    <div className={styles.goalMeta}>{goal.linkedItem ? <span>Linked To {goal.linkedItem.name}</span> : null}{goal.goalType === "debt" && goal.monthlyContribution > 0 ? <span>Planned Extra Payment: {currency(goal.monthlyContribution)} / Month</span> : null}{goal.targetDate ? <span>Target Date {dateLabel(goal.targetDate)}</span> : null}{goal.targetDate && goal.goalType === "savings" && goal.requiredMonthly > 0 ? <span>Needed: {currency(goal.requiredMonthly)} / Month</span> : null}{goal.targetDate && goal.goalType === "debt" ? <span>{goal.requiredExtra > 0 ? `Extra Needed: ${currency(goal.requiredExtra)} / Month` : "Current payoff pace should meet this date."}</span> : null}<span>{goal.timeline}</span></div>
  </article>;
}
