"use client";

import { subscriptionsViewSchema, type SubscriptionsView, type SubscriptionView } from "@clearpath/validation";
import { Bot, Check, ChevronDown, Download, ExternalLink, FileSpreadsheet, Plus, RefreshCw, Search, Sparkles, X } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import { AuthenticatedShell } from "../authenticated-shell";
import styles from "./subscriptions.module.css";

export type SubscriptionQuery = { q: string; status: string; sort: string };

const currency = (value: number, digits = 2) => new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: digits, maximumFractionDigits: digits }).format(value);
const dateLabel = (value: string | null) => value ? new Date(`${value}T12:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }) : "Not set";

async function responseMessage(response: Response, fallback: string) {
  const body = await response.json().catch(() => null) as { message?: string } | null;
  return body?.message || fallback;
}

function sortedSubscriptions(data: SubscriptionsView, query: SubscriptionQuery) {
  const search = query.q.toLowerCase();
  const rows = data.subscriptions.filter((row) => (
    (!search || `${row.name} ${row.serviceCategory} ${row.cycle}`.toLowerCase().includes(search))
    && ((query.status === "all" && row.status !== "ignored") || row.status === query.status)
  ));
  return rows.sort((left, right) => {
    if (query.sort === "amount_desc") return right.monthlyAmount - left.monthlyAmount;
    if (query.sort === "amount_asc") return left.monthlyAmount - right.monthlyAmount || left.name.localeCompare(right.name);
    if (query.sort === "next_asc") return (left.nextChargeDate ?? "9999-12-31").localeCompare(right.nextChargeDate ?? "9999-12-31") || left.name.localeCompare(right.name);
    if (query.sort === "next_desc") return (right.nextChargeDate ?? "0000-01-01").localeCompare(left.nextChargeDate ?? "0000-01-01") || right.name.localeCompare(left.name);
    if (query.sort === "confidence_desc") return right.confidence - left.confidence;
    if (query.sort === "confidence_asc") return left.confidence - right.confidence || left.name.localeCompare(right.name);
    if (query.sort === "name_az") return left.name.localeCompare(right.name);
    if (query.sort === "name_za") return right.name.localeCompare(left.name);
    const leftPriority = left.monthlyAmount * (left.status === "review" ? 1.4 : left.replaceable ? 1.2 : 1);
    const rightPriority = right.monthlyAmount * (right.status === "review" ? 1.4 : right.replaceable ? 1.2 : 1);
    return rightPriority - leftPriority;
  });
}

export function SubscriptionsWorkspace({ query }: { query: SubscriptionQuery }) {
  const router = useRouter();
  const [data, setData] = useState<SubscriptionsView | null>(null);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const [addOpen, setAddOpen] = useState(false);

  const load = useCallback(async () => {
    setError("");
    try {
      const response = await fetch("/api/subscriptions", { cache: "no-store" });
      if (!response.ok) throw new Error(await responseMessage(response, "We could not load subscriptions."));
      const parsed = subscriptionsViewSchema.safeParse(await response.json());
      if (!parsed.success) throw new Error("Subscription data did not match the expected contract.");
      setData(parsed.data);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "We could not load subscriptions.");
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const canEdit = Boolean(data && (data.session.primaryAccountHolder || data.session.subject.householdRole !== "viewer"));
  const rows = useMemo(() => data ? sortedSubscriptions(data, query) : [], [data, query]);

  const mutate = async (url: string, options: RequestInit, successMessage: string) => {
    setBusy(true); setError(""); setStatus("");
    try {
      const response = await fetch(url, { ...options, headers: { "content-type": "application/json", ...(options.headers ?? {}) } });
      if (!response.ok) throw new Error(await responseMessage(response, "That change could not be saved."));
      const body = await response.json().catch(() => ({})) as Record<string, unknown>;
      setStatus(successMessage.replace(":count", String(body.syncedCount ?? body.imported ?? "")));
      await load();
      return body;
    } catch (mutationError) {
      setError(mutationError instanceof Error ? mutationError.message : "That change could not be saved.");
      return null;
    } finally { setBusy(false); }
  };

  const updateQuery = (next: SubscriptionQuery) => {
    const params = new URLSearchParams();
    if (next.q) params.set("q", next.q);
    if (next.status !== "all") params.set("status", next.status);
    if (next.sort !== "priority") params.set("sort", next.sort);
    router.push(`/subscriptions${params.size ? `?${params.toString()}` : ""}`);
  };

  const applyFilters = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    updateQuery({ q: String(form.get("q") ?? "").trim().toLowerCase(), status: String(form.get("status") ?? "all"), sort: String(form.get("sort") ?? "priority") });
  };

  const addManual = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const result = await mutate("/api/subscriptions", { method: "POST", body: JSON.stringify({ name: form.get("name"), amount: Number(form.get("amount")), cycle: form.get("cycle"), nextChargeDate: form.get("next_charge_date") || null, notes: form.get("notes") || null }) }, "Subscription added.");
    if (result) { formElement.reset(); setAddOpen(false); }
  };

  const importCsv = async (file: File | undefined) => {
    if (!file) return;
    const csvText = await file.text();
    await mutate("/api/subscription-imports", { method: "POST", body: JSON.stringify({ csvText }) }, ":count scanner transactions imported.");
  };

  const content = (
    <main className={styles.page}>
      <header className={styles.pageHeader}>
        <div><p className={styles.eyebrow}>Recurring Spend</p><h1>Subscriptions</h1><p>Review consumer subscriptions and open the right place to manage them.</p></div>
        <div className={styles.headerActions}>
          <Link href="/api/subscriptions/export" className={styles.secondaryButton}><Download size={16} aria-hidden="true" />Export CSV</Link>
          <button type="button" className={styles.primaryButton} disabled={!canEdit} onClick={() => setAddOpen((open) => !open)}><Plus size={16} aria-hidden="true" />Add Subscription</button>
        </div>
      </header>

      {error ? <div className={styles.error} role="alert">{error}</div> : null}
      {status ? <div className={styles.status} role="status">{status}</div> : null}
      {data && !canEdit ? <div className={styles.viewerNotice}>Shared viewer access is read-only.</div> : null}

      <div className={styles.callout}>Consumer subscriptions include streaming, software, cloud storage, news, fitness, and memberships. Household bills and loan payments stay in Budgets.</div>

      {data ? <section className={styles.stats} aria-label="Subscription summary">
        <article><span>Monthly Subscriptions</span><strong>{currency(data.summary.monthlyTotal, 0)}</strong><small>{data.summary.activeCount} active or managed</small></article>
        <article><span>Annualized Cost</span><strong>{currency(data.summary.annualTotal, 0)}</strong><small>Projected if unchanged</small></article>
        <article><span>Potential Savings</span><strong className={styles.positive}>{currency(data.summary.potentialSavings, 0)}</strong><small>Review-ready or replaceable</small></article>
        <article><span>Manage Links Saved</span><strong>{data.summary.manageLinkCount}</strong><small>Saved portals</small></article>
      </section> : null}

      {addOpen && data && canEdit ? <section className={styles.addSection} aria-labelledby="add-subscriptions-title">
        <div className={styles.sectionHeading}><div><h2 id="add-subscriptions-title">Add Subscriptions</h2><p>{data.summary.transactionCount} transactions available to scan</p></div><button type="button" className={styles.iconButton} title="Close" aria-label="Close add subscriptions" onClick={() => setAddOpen(false)}><X size={18} /></button></div>
        <div className={styles.addGrid}>
          <div className={styles.addPanel}><h3>Scan Transactions</h3><p>Run after syncing, importing, or categorizing Consumer Subscriptions.</p><div className={styles.scanFacts}><span><strong>{data.subscriptions.length}</strong>Likely Subscriptions</span><span><strong>{data.summary.averageConfidence}%</strong>Average Confidence</span></div><button type="button" className={styles.primaryButton} disabled={busy} onClick={() => void mutate("/api/subscriptions/scan", { method: "POST", body: "{}" }, ":count subscriptions found or refreshed.")}><RefreshCw size={16} />Run Scan</button><label className={styles.fileButton}><FileSpreadsheet size={16} />Import CSV<input type="file" accept=".csv,text/csv" onChange={(event) => void importCsv(event.target.files?.[0])} /></label></div>
          <form className={styles.manualForm} onSubmit={addManual}><h3>Manually Add</h3><label>Service<input name="name" placeholder="Netflix, ChatGPT, Dropbox..." required /></label><div className={styles.inputPair}><label>Amount<input name="amount" inputMode="decimal" required /></label><label>Cycle<select name="cycle" defaultValue="Monthly">{data.cycles.map((cycle) => <option key={cycle}>{cycle}</option>)}</select></label></div><label>Next Charge<input type="date" name="next_charge_date" /></label><label>Notes<textarea name="notes" rows={2} /></label><button type="submit" className={styles.primaryButton} disabled={busy}>Add Subscription</button></form>
        </div>
      </section> : null}

      {data ? <form className={styles.toolbar} onSubmit={applyFilters}>
        <label className={styles.searchField}><Search size={16} aria-hidden="true" /><span>Search</span><input type="search" name="q" defaultValue={query.q} placeholder="Netflix, software, annual..." /></label>
        <label>Status<select name="status" defaultValue={query.status}><option value="all">All Active/Managed</option>{Object.entries(data.statuses).filter(([value]) => value !== "canceling").map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label>Sort<select name="sort" defaultValue={query.sort}><option value="priority">Priority</option><option value="name_az">Service: A to Z</option><option value="name_za">Service: Z to A</option><option value="amount_desc">Monthly: High to Low</option><option value="amount_asc">Monthly: Low to High</option><option value="next_asc">Next Charge: Soonest</option><option value="next_desc">Next Charge: Latest</option><option value="confidence_desc">Confidence: High to Low</option><option value="confidence_asc">Confidence: Low to High</option></select></label>
        <button type="submit" className={styles.secondaryButton}>Apply</button>
      </form> : null}

      <section className={styles.listSection} aria-labelledby="subscription-list-title">
        <div className={styles.sectionHeading}><div><h2 id="subscription-list-title">Subscription Review</h2><p>{data ? `${rows.length} of ${data.subscriptions.length} subscriptions` : "Loading subscriptions"}</p></div></div>
        {!data ? <div className={styles.empty}><RefreshCw className={styles.spin} size={20} />Loading subscriptions...</div> : null}
        {data && !rows.length ? <div className={styles.empty}>No subscriptions match these filters.</div> : null}
        {data ? rows.map((subscription) => <SubscriptionRow key={subscription.id} subscription={subscription} data={data} canEdit={canEdit} busy={busy} onMutate={mutate} />) : null}
      </section>
    </main>
  );

  return data ? <AuthenticatedShell session={data.session}>{content}</AuthenticatedShell> : content;
}

function SubscriptionRow({ subscription, data, canEdit, busy, onMutate }: { subscription: SubscriptionView; data: SubscriptionsView; canEdit: boolean; busy: boolean; onMutate: (url: string, options: RequestInit, message: string) => Promise<Record<string, unknown> | null> }) {
  const [detailsOpen, setDetailsOpen] = useState(false);
  const visibleStatus = subscription.status === "canceling" ? "active" : subscription.status;
  const upcoming = data.upcomingSubscriptionIds.includes(subscription.id);
  const opportunity = data.opportunities.find((row) => row.subscriptionId === subscription.id);
  return <article className={styles.subscriptionRow}>
    <div className={styles.serviceIcon}>{subscription.name.slice(0, 2).toUpperCase()}</div>
    <div className={styles.serviceInfo}><strong>{subscription.name}</strong><span>{subscription.serviceCategory} · {subscription.isManual ? "Manually added" : "Detected from transactions"}</span><div className={styles.badges}>{upcoming ? <span>Upcoming Charge</span> : null}{subscription.status === "review" ? <span>Confirm Detection</span> : null}{opportunity ? <span>{opportunity.reason}</span> : null}</div></div>
    <div className={styles.amount}><strong>{currency(subscription.monthlyAmount)}/mo</strong><label>{currency(subscription.amount)}<select aria-label={`Update ${subscription.name} cycle`} value={subscription.cycle} disabled={!canEdit || busy} onChange={(event) => void onMutate(`/api/subscriptions/${subscription.id}`, { method: "PATCH", body: JSON.stringify({ cycle: event.target.value }) }, "Subscription cycle updated.")}>{data.cycles.map((cycle) => <option key={cycle}>{cycle}</option>)}</select></label></div>
    <div className={styles.confidence}><span>Confidence <strong>{Math.round(subscription.confidence * 100)}%</strong></span><div><i className={subscription.confidence >= .78 ? styles.good : subscription.confidence >= .58 ? styles.caution : styles.low} style={{ width: `${Math.round(subscription.confidence * 100)}%` }} /></div></div>
    <span className={`${styles.statusPill} ${visibleStatus === "review" ? styles.review : visibleStatus === "active" ? styles.active : styles.inactive}`}>{data.statuses[visibleStatus] ?? visibleStatus}</span>
    <div className={styles.rowActions}><button type="button" className={styles.secondaryButton} aria-expanded={detailsOpen} onClick={() => setDetailsOpen((open) => !open)}>Details<ChevronDown size={15} /></button>{subscription.status === "review" ? <button type="button" className={styles.primaryButton} disabled={!canEdit || busy} onClick={() => void onMutate(`/api/subscriptions/${subscription.id}`, { method: "PATCH", body: JSON.stringify({ status: "active" }) }, "Subscription confirmed.")}><Check size={15} />Confirm</button> : subscription.status === "canceled" || subscription.status === "ignored" ? <button type="button" className={styles.secondaryButton} disabled={!canEdit || busy} onClick={() => void onMutate(`/api/subscriptions/${subscription.id}`, { method: "PATCH", body: JSON.stringify({ status: "active" }) }, "Subscription reactivated.")}>Reactivate</button> : subscription.cancelUrl ? <a href={subscription.cancelUrl} target="_blank" rel="noreferrer" className={styles.primaryButton}>Manage<ExternalLink size={15} /></a> : <button type="button" className={styles.secondaryButton} onClick={() => setDetailsOpen(true)}>Add Website</button>}</div>
    {detailsOpen ? <SubscriptionDetails subscription={subscription} data={data} canEdit={canEdit} busy={busy} onClose={() => setDetailsOpen(false)} onMutate={onMutate} /> : null}
  </article>;
}

type LinkHelp = { message: string; candidates: Array<{ title: string; url: string; reason: string; confidence: string }> };

function SubscriptionDetails({ subscription, data, canEdit, busy, onClose, onMutate }: { subscription: SubscriptionView; data: SubscriptionsView; canEdit: boolean; busy: boolean; onClose(): void; onMutate: (url: string, options: RequestInit, message: string) => Promise<Record<string, unknown> | null> }) {
  const [manageUrl, setManageUrl] = useState(subscription.cancelUrl ?? "");
  const [notes, setNotes] = useState(subscription.notes ?? "");
  const [selectedStatus, setSelectedStatus] = useState(subscription.status);
  const [linkHelp, setLinkHelp] = useState<LinkHelp | null>(null);
  const [linkError, setLinkError] = useState("");
  const aiFeature = data.session.featureAccess.find((row) => row.feature === "ai_coach");
  const findLink = async () => {
    setLinkError("");
    const response = await fetch(`/api/subscriptions/${subscription.id}/link-help`, { method: "POST", headers: { "content-type": "application/json" }, body: "{}" });
    if (!response.ok) { setLinkError(await responseMessage(response, "We could not find a management link.")); return; }
    setLinkHelp(await response.json() as LinkHelp);
  };
  return <div className={styles.details}>
    <div className={styles.detailHeader}><div><h3>{subscription.name} Details</h3><p>{subscription.cycle} · {currency(subscription.annualAmount)} annualized · next {dateLabel(subscription.nextChargeDate)}</p></div><button type="button" className={styles.iconButton} title="Close" aria-label={`Close ${subscription.name} details`} onClick={onClose}><X size={18} /></button></div>
    <div className={styles.detailGrid}>
      <div><h4>Status And Notes</h4><label>Status<select value={selectedStatus} disabled={!canEdit} onChange={(event) => setSelectedStatus(event.target.value)}>{Object.entries(data.statuses).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><label>Notes<textarea rows={3} value={notes} disabled={!canEdit} onChange={(event) => setNotes(event.target.value)} /></label><button type="button" className={styles.secondaryButton} disabled={!canEdit || busy} onClick={() => void onMutate(`/api/subscriptions/${subscription.id}`, { method: "PATCH", body: JSON.stringify({ status: selectedStatus, notes }) }, "Subscription updated.")}>Save Status</button></div>
      <div><h4>Management Website</h4><label>Website<input type="url" value={manageUrl} disabled={!canEdit} placeholder="https://example.com/account" onChange={(event) => setManageUrl(event.target.value)} /></label><div className={styles.linkActions}><button type="button" className={styles.secondaryButton} disabled={!canEdit || busy} onClick={() => void onMutate(`/api/subscriptions/${subscription.id}`, { method: "PATCH", body: JSON.stringify({ cancelUrl: manageUrl }) }, "Subscription website updated.")}>Save Website</button>{manageUrl ? <a href={manageUrl} target="_blank" rel="noreferrer" className={styles.primaryButton}>Open<ExternalLink size={15} /></a> : null}</div>{aiFeature?.enabled && !aiFeature.hidden && canEdit ? <button type="button" className={styles.aiButton} disabled={busy} onClick={() => void findLink()}><Bot size={16} />Find Official Link</button> : aiFeature && !aiFeature.hidden && data.session.primaryAccountHolder ? <Link href="/select-plan" className={styles.aiButton}><Sparkles size={16} />Upgrade For AI Link Help</Link> : null}{linkError ? <div className={styles.inlineError}>{linkError}</div> : null}{linkHelp ? <div className={styles.linkResults}><p>{linkHelp.message}</p>{linkHelp.candidates.map((candidate) => <article key={candidate.url}><div><strong>{candidate.title}</strong><span>{candidate.reason} · {candidate.confidence} confidence</span></div><button type="button" className={styles.secondaryButton} onClick={() => setManageUrl(candidate.url)}>Use Link</button></article>)}</div> : null}</div>
    </div>
    <div className={styles.evidence}><h4>Detected Transaction Evidence</h4>{subscription.evidence.length ? subscription.evidence.map((item, index) => <div key={item.id ?? `${item.date}-${index}`}><span><strong>{item.description || "Manual Entry"}</strong><small>{dateLabel(item.date)} · {currency(item.amount ?? 0)}</small></span>{item.id ? <div><Link href={`/transactions?q=${encodeURIComponent(item.description ?? "")}`}>Review</Link><button type="button" disabled={!canEdit || busy} onClick={() => window.confirm("Ignore this transaction for future subscription scans?") && void onMutate(`/api/subscriptions/${subscription.id}/evidence/${item.id}/ignore`, { method: "POST", body: "{}" }, "Transaction ignored for future scans.")}>Ignore</button></div> : <small>Manual Entry</small>}</div>) : <p>No transaction evidence is attached yet.</p>}</div>
  </div>;
}
