"use client";

import { plannerGuidanceSchema, plannerViewSchema, type PlannerGuidance, type PlannerView } from "@clearpath/validation";
import { BrainCircuit, RefreshCw, Save, ShieldCheck, Sparkles } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import { AuthenticatedShell } from "../authenticated-shell";
import styles from "./planner.module.css";

const targets: Record<string, string> = {
  dashboard: "/dashboard",
  monthly_plan_forecast: "/monthly-plan?section=forecast",
  cash_projections: "/cash-projections",
  subscriptions: "/subscriptions",
  monthly_plan_budgets: "/monthly-plan?section=budgets",
  goals: "/goals",
  retirement_plan: "/retirement-plan",
};

async function responseMessage(response: Response, fallback: string) {
  const body = await response.json().catch(() => null) as { message?: string } | null;
  return body?.message || fallback;
}

function canEdit(view: PlannerView) {
  return view.session.primaryAccountHolder || view.session.subject.householdRole !== "viewer";
}

export function PlannerWorkspace() {
  const router = useRouter();
  const [view, setView] = useState<PlannerView | null>(null);
  const [provider, setProvider] = useState("");
  const [model, setModel] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState<"load" | "save" | "generate" | "">("load");

  const applyGuidance = useCallback((guidance: PlannerGuidance) => {
    setView((current) => current ? { ...current, guidance } : current);
    setProvider(guidance.selectedProvider);
    setModel(guidance.selectedModel);
  }, []);

  const load = useCallback(async () => {
    setBusy("load");
    setError("");
    try {
      const response = await fetch("/api/planner", { cache: "no-store" });
      if (response.status === 403) {
        router.replace("/select-plan");
        return;
      }
      if (!response.ok) throw new Error(await responseMessage(response, "We could not load AI Planner."));
      const parsed = plannerViewSchema.safeParse(await response.json());
      if (!parsed.success) throw new Error("Planner data did not match the expected contract.");
      setView(parsed.data);
      setProvider(parsed.data.guidance.selectedProvider);
      setModel(parsed.data.guidance.selectedModel);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "We could not load AI Planner.");
    } finally {
      setBusy("");
    }
  }, [router]);

  useEffect(() => { void load(); }, [load]);

  const providerOption = useMemo(
    () => view?.guidance.modelOptions.find((option) => option.key === provider) ?? null,
    [provider, view],
  );

  const changeProvider = (nextProvider: string) => {
    const option = view?.guidance.modelOptions.find((row) => row.key === nextProvider);
    setProvider(nextProvider);
    if (option && !option.models.some((row) => row.id === model)) setModel(option.models[0]?.id ?? "");
  };

  const savePreference = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setBusy("save");
    setError("");
    setNotice("");
    try {
      const response = await fetch("/api/planner/preferences", { method: "PATCH", headers: { "content-type": "application/json" }, body: JSON.stringify({ provider, model }) });
      if (!response.ok) throw new Error(await responseMessage(response, "We could not save that AI preference."));
      const parsed = plannerGuidanceSchema.safeParse(await response.json());
      if (!parsed.success) throw new Error("Planner data did not match the expected contract.");
      applyGuidance(parsed.data);
      setNotice("AI model preference saved.");
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "We could not save that AI preference.");
    } finally {
      setBusy("");
    }
  };

  const generate = async () => {
    setBusy("generate");
    setError("");
    setNotice("");
    try {
      const response = await fetch("/api/planner/guidance", { method: "POST" });
      if (!response.ok) throw new Error(await responseMessage(response, "We could not generate AI guidance."));
      const parsed = plannerGuidanceSchema.safeParse(await response.json());
      if (!parsed.success) throw new Error("Planner data did not match the expected contract.");
      applyGuidance(parsed.data);
      setNotice("Financial coaching updated.");
    } catch (generateError) {
      setError(generateError instanceof Error ? generateError.message : "We could not generate AI guidance.");
    } finally {
      setBusy("");
    }
  };

  const content = <main className={styles.page}>
    <header className={styles.pageHeader}>
      <div><p className={styles.eyebrow}>ClearPath Premier</p><h1>AI Planner</h1><p>Planner-only analytics, forecasting, and educational account-awareness coaching with strict advice guardrails.</p></div>
      <span className={styles.premierBadge}><Sparkles size={14} aria-hidden="true" />ClearPath Premier</span>
    </header>

    {error ? <div className={styles.error} role="alert"><span>{error}</span>{!view ? <button type="button" onClick={() => void load()}>Try Again</button> : null}</div> : null}
    {notice ? <div className={styles.notice} role="status">{notice}</div> : null}
    {!view && busy === "load" ? <div className={styles.loading}><RefreshCw className={styles.spin} size={20} />Loading AI Planner...</div> : null}

    {view ? <div className={styles.content}>
      {!canEdit(view) ? <div className={styles.viewerNotice}>You can review saved coaching and use Ask AI Coach. An owner or editor can generate new guidance or change the model preference.</div> : null}
      <section className={styles.topGrid}>
        <article className={styles.panel}>
          <header><div><h2>AI Model Preference</h2><p>Choose the configured provider used for new coaching.</p></div><span>{view.guidance.source}</span></header>
          <form className={styles.preferenceForm} onSubmit={(event) => void savePreference(event)}>
            <div className={styles.formGrid}>
              <label><span>AI Provider</span><select aria-label="AI Provider" value={provider} disabled={!canEdit(view) || busy !== ""} onChange={(event) => changeProvider(event.target.value)}>{view.guidance.modelOptions.map((option) => <option value={option.key} key={option.key}>{option.label}{option.configured ? "" : " (key not configured)"}</option>)}</select></label>
              <label><span>Model</span><select aria-label="Model" value={model} disabled={!canEdit(view) || busy !== ""} onChange={(event) => setModel(event.target.value)}>{providerOption?.models.map((option) => <option value={option.id} key={option.id}>{option.label}</option>)}</select></label>
            </div>
            <button type="submit" disabled={!canEdit(view) || busy !== ""}><Save size={15} aria-hidden="true" />{busy === "save" ? "Saving..." : "Save Preference"}</button>
          </form>
          <div className={styles.guardrail}><ShieldCheck size={19} aria-hidden="true" /><div><strong>Guardrail Boundary</strong><p>Planner AI can explain cash flow, budgeting, forecasting, subscriptions, goals, and account types to review. It cannot recommend securities, allocations, trades, market timing, or personalized investment, tax, legal, insurance, or credit decisions.</p></div></div>
          {view.guidance.status === "fallback" || view.guidance.status === "ready" ? <p className={styles.guidanceState}>{view.guidance.message}</p> : null}
        </article>

        <article className={styles.panel}>
          <header><div><h2>Investment-Option Awareness</h2><p>Educational account context only.</p></div><span>Education Only</span></header>
          <div className={styles.educationBody}>
            <div className={styles.educationCallout}>This area may surface account types or contribution opportunities to review, such as employer plans, IRA/Roth IRA eligibility, HSAs, 529s, or taxable brokerage basics. It does not tell you which account, security, allocation, or contribution strategy is right for you.</div>
            <ul><li>No tickers, securities, crypto, fund picks, or allocation percentages.</li><li>No buy, sell, hold, rebalance, or market-timing instructions.</li><li>Review eligibility, limits, and tax treatment with qualified professionals.</li></ul>
          </div>
        </article>
      </section>

      <section className={styles.coachingPanel}>
        <header><div><h2>Financial Coaching</h2><p>{view.guidance.message}{view.guidance.generatedAt ? ` Last generated ${new Date(view.guidance.generatedAt).toLocaleString()}.` : ""}</p></div><div><button type="button" disabled={!canEdit(view) || busy !== ""} onClick={() => void generate()}><BrainCircuit size={16} aria-hidden="true" />{busy === "generate" ? "Generating..." : "Generate AI Guidance"}</button><span>{view.guidance.model}</span></div></header>
        {view.guidance.items.length ? <div className={styles.coachingList}>{view.guidance.items.map((item, index) => <article className={styles.coachingItem} key={`${item.title}-${index}`}><div><h3>{item.title}</h3><span className={item.level === "alert" ? styles.alertLevel : item.level === "warning" ? styles.warningLevel : styles.goodLevel}>{item.level}</span></div><p>{item.body}</p>{item.action ? <Link href={targets[item.action.target] ?? "/dashboard"}>{item.action.label}</Link> : null}</article>)}</div> : <div className={styles.empty}>No Financial Coaching is available yet. Add income, expenses, transactions, goals, or forecast items to make this area more useful.</div>}
      </section>
    </div> : null}
  </main>;

  return view ? <AuthenticatedShell session={view.session}>{content}</AuthenticatedShell> : content;
}
