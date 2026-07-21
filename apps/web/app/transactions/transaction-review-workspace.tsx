"use client";

import { transactionReviewViewSchema, type TransactionReviewView } from "@clearpath/validation";
import { ChevronLeft, ChevronRight, Filter, Plus, RefreshCw, Tags, Upload } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";

import { usePendingMutations } from "@/lib/use-pending-mutations";

import { AuthenticatedShell } from "../authenticated-shell";
import { TransactionImportPanel } from "./transaction-import-panel";
import { TransactionRow } from "./transaction-row";
import styles from "./transactions.module.css";

export type TransactionQuery = {
  q: string; categoryIds: string[]; categoryNames: string; accountIds: string[];
  minAmount: string; maxAmount: string; month: string; ids: string; sort: string; page: string; importMode: boolean;
};

const sortOptions = {
  date_desc: "Date: Newest First", date_asc: "Date: Oldest First",
  description_az: "Description: A To Z", description_za: "Description: Z To A",
  amount_desc: "Amount: High To Low", amount_asc: "Amount: Low To High",
};

async function responseMessage(response: Response, fallback: string) {
  const body = await response.json().catch(() => null) as { message?: string } | null;
  return body?.message || fallback;
}

function queryParams(query: TransactionQuery) {
  const params = new URLSearchParams();
  if (query.q) params.set("q", query.q);
  query.categoryIds.forEach((value) => params.append("category_id", value));
  if (query.categoryNames) params.set("category_names", query.categoryNames);
  query.accountIds.forEach((value) => params.append("account_id", value));
  if (query.minAmount) params.set("min_amount", query.minAmount);
  if (query.maxAmount) params.set("max_amount", query.maxAmount);
  if (query.month) params.set("month", query.month);
  if (query.ids) params.set("ids", query.ids);
  if (query.sort !== "date_desc") params.set("sort", query.sort);
  if (query.page !== "1") params.set("page", query.page);
  if (query.importMode) params.set("import", "csv");
  return params;
}

export function TransactionReviewWorkspace({ query }: { query: TransactionQuery }) {
  const router = useRouter();
  const [data, setData] = useState<TransactionReviewView | null>(null);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const { isPendingMatching, anyPending, start, stop } = usePendingMutations();
  const [filtersOpen, setFiltersOpen] = useState(Boolean(query.q || query.categoryIds.length || query.accountIds.length || query.minAmount || query.maxAmount || query.month));
  const [importOpen, setImportOpen] = useState(query.importMode);
  const refreshedKey = useRef<string | null>(null);
  const serializedQuery = useMemo(() => queryParams(query).toString(), [query]);

  const load = useCallback(async (refreshStale: boolean) => {
    setError("");
    try {
      if (refreshStale && refreshedKey.current !== serializedQuery) {
        refreshedKey.current = serializedQuery;
        const refresh = await fetch("/api/plaid-items/refresh-stale", { method: "POST" });
        if (!refresh.ok && refresh.status !== 403) setStatus(await responseMessage(refresh, "Live bank refresh could not complete."));
      }
      const response = await fetch(`/api/transactions${serializedQuery ? `?${serializedQuery}` : ""}`, { cache: "no-store" });
      if (!response.ok) throw new Error(await responseMessage(response, "We could not load transactions."));
      const parsed = transactionReviewViewSchema.safeParse(await response.json());
      if (!parsed.success) throw new Error("Transaction data did not match the expected contract.");
      setData(parsed.data);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "We could not load transactions.");
    }
  }, [serializedQuery]);

  useEffect(() => { void load(true); }, [load]);

  const canEdit = Boolean(data && (data.session.primaryAccountHolder || data.session.subject.householdRole !== "viewer"));
  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.perPage)) : 1;

  const navigate = (next: Partial<TransactionQuery>) => {
    const merged = { ...query, ...next };
    const params = queryParams(merged);
    router.push(`/transactions${params.size ? `?${params.toString()}` : ""}`);
  };

  const mutate = async (url: string, options: RequestInit, successMessage: string, redirect?: string) => {
    // The URL identifies the row, so concurrent edits on different rows stay
    // independent instead of sharing one global busy flag.
    const key = `${options.method ?? "GET"} ${url}`;
    start(key); setError(""); setStatus("");
    try {
      const response = await fetch(url, { ...options, headers: { "content-type": "application/json", ...(options.headers ?? {}) } });
      if (!response.ok) throw new Error(await responseMessage(response, successMessage));
      const body = await response.json().catch(() => ({})) as Record<string, unknown>;
      setStatus(successMessage);
      if (redirect) router.push(redirect.replace(":id", String(body.fixedExpenseItemId ?? "")));
      else await load(false);
      return body;
    } catch (mutationError) {
      setError(mutationError instanceof Error ? mutationError.message : "That change could not be saved.");
      return null;
    } finally { stop(key); }
  };

  const applyFilters = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    navigate({
      q: String(form.get("q") ?? ""), categoryIds: form.getAll("category_id").map(String), accountIds: form.getAll("account_id").map(String),
      minAmount: String(form.get("min_amount") ?? ""), maxAmount: String(form.get("max_amount") ?? ""), month: String(form.get("month") ?? ""),
      sort: String(form.get("sort") ?? "date_desc"), page: "1",
    });
  };

  const createCategory = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const result = await mutate("/api/categories", { method: "POST", body: JSON.stringify({ name: form.get("name"), kind: form.get("kind"), activateBudget: true }) }, "Category created.");
    if (result) event.currentTarget.reset();
  };

  const content = (
    <main className={styles.page}>
      <header className={styles.pageHeader}>
        <div><p className={styles.eyebrow}>Transaction Review</p><h1>Transactions</h1><p>{data ? `${data.total.toLocaleString()} records` : "Loading records"}</p></div>
        <div className={styles.headerActions}>
          <Link href="/category-rules" className={styles.secondaryButton}><Tags size={16} aria-hidden="true" />Create Rule</Link>
          <button type="button" className={styles.secondaryButton} onClick={() => setFiltersOpen((open) => !open)} aria-expanded={filtersOpen}><Filter size={16} aria-hidden="true" />Filters</button>
          <button type="button" className={styles.primaryButton} onClick={() => setImportOpen((open) => !open)} disabled={!canEdit}><Upload size={16} aria-hidden="true" />Import & Sync</button>
        </div>
      </header>

      {error ? <div className={styles.error} role="alert">{error}</div> : null}
      {status ? <div className={styles.status} role="status">{status}</div> : null}
      {data && !canEdit ? <div className={styles.viewerNotice}>Shared viewer access is read-only.</div> : null}

      {filtersOpen && data ? (
        <form className={styles.filters} onSubmit={applyFilters}>
          <label className={styles.searchField}>Search<input name="q" type="search" defaultValue={query.q} placeholder="Merchant or description" /></label>
          <label>Month<input name="month" type="month" defaultValue={query.month} /></label>
          <label>Categories<select name="category_id" multiple defaultValue={query.categoryIds}>{data.categories.map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}</select></label>
          <label>Accounts<select name="account_id" multiple defaultValue={query.accountIds}>{data.accounts.map((account) => <option key={account.id} value={account.id}>{account.institution ? `${account.institution} - ` : ""}{account.name}</option>)}</select></label>
          <label>Minimum Amount<input name="min_amount" inputMode="decimal" defaultValue={query.minAmount} /></label>
          <label>Maximum Amount<input name="max_amount" inputMode="decimal" defaultValue={query.maxAmount} /></label>
          <label>Sort<select name="sort" defaultValue={query.sort}>{Object.entries(sortOptions).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
          <div className={styles.filterActions}><button className={styles.primaryButton} type="submit">Apply</button><button className={styles.ghostButton} type="button" onClick={() => router.push("/transactions")}>Clear</button></div>
        </form>
      ) : null}

      {importOpen && data ? <TransactionImportPanel plaidItems={data.plaidItems} canEdit={canEdit} busy={anyPending} onMutate={mutate} onImported={() => { setImportOpen(false); navigate({ importMode: false, page: "1" }); }} /> : null}

      {data?.duplicateSuggestions.length ? (
        <section className={styles.duplicateSection} aria-labelledby="duplicates-title">
          <div className={styles.sectionHeading}><div><h2 id="duplicates-title">Possible Duplicates</h2><p>{data.duplicateSuggestions.length} pair{data.duplicateSuggestions.length === 1 ? "" : "s"} to review</p></div></div>
          <div className={styles.duplicateList}>{data.duplicateSuggestions.map((duplicate) => (
            <article key={`${duplicate.plaidTransactionId}-${duplicate.manualTransactionId}`} className={styles.duplicateRow}>
              <div><strong>{duplicate.plaidTransaction.displayMerchant}</strong><span>Bank record · {duplicate.plaidTransaction.postedDate}</span></div>
              <div><strong>{duplicate.manualTransaction.displayMerchant}</strong><span>Manual record · {duplicate.manualTransaction.postedDate}</span></div>
              <span className={styles.confidence}>{duplicate.confidenceLabel}</span>
              <button type="button" className={styles.secondaryButton} disabled={!canEdit || anyPending} onClick={() => void mutate("/api/transactions/duplicates/merge", { method: "POST", body: JSON.stringify({ firstTransactionId: duplicate.plaidTransactionId, secondTransactionId: duplicate.manualTransactionId }) }, "Duplicate records merged.")}>Merge</button>
            </article>
          ))}</div>
        </section>
      ) : null}

      <section className={styles.transactionSection} aria-labelledby="transaction-list-title">
        <div className={styles.sectionHeading}>
          <div><h2 id="transaction-list-title">Review Queue</h2><p>{query.ids ? "Selected planning transactions" : "Posted and pending activity"}</p></div>
          {query.ids ? <button type="button" className={styles.ghostButton} onClick={() => navigate({ ids: "", page: "1" })}>Clear Review Filter</button> : null}
        </div>
        <div className={styles.tableHeader}><span>Date</span><span>Description</span><span>Category</span><span>Amount</span></div>
        {!data ? <div className={styles.empty}><RefreshCw size={20} className={styles.spin} aria-hidden="true" />Loading transactions...</div> : null}
        {data && !data.items.length ? <div className={styles.empty}>No transactions match these filters.</div> : null}
        {data?.items.map((transaction) => (
          <TransactionRow key={transaction.id} transaction={transaction} categories={data.categories} budgetAction={data.budgetActions[String(transaction.id)]} amortizationAction={data.amortizationActions[String(transaction.id)]} recurring={data.recurringTransactionIds.includes(transaction.id)} canEdit={canEdit} busy={isPendingMatching(`/transactions/${transaction.id}`)} onMutate={mutate} />
        ))}
        {data && totalPages > 1 ? <nav className={styles.pagination} aria-label="Transaction pages"><button type="button" disabled={data.page <= 1} onClick={() => navigate({ page: String(data.page - 1) })}><ChevronLeft size={17} /><span>Previous</span></button><strong>Page {data.page} of {totalPages}</strong><button type="button" disabled={data.page >= totalPages} onClick={() => navigate({ page: String(data.page + 1) })}><span>Next</span><ChevronRight size={17} /></button></nav> : null}
      </section>

      {data && canEdit ? (
        <details className={styles.categoryManager}>
          <summary><Tags size={17} aria-hidden="true" />Manage Categories</summary>
          <form className={styles.categoryCreate} onSubmit={createCategory}><label>Name<input name="name" maxLength={80} required /></label><label>Type<select name="kind" defaultValue="expense"><option value="expense">Expense</option><option value="income">Income</option></select></label><button type="submit" className={styles.primaryButton} disabled={anyPending}><Plus size={16} />Add Category</button></form>
          <div className={styles.categoryList}>{data.categories.filter((category) => category.canManage).map((category) => <CategoryManagerRow key={category.id} category={category} categories={data.categories} busy={anyPending} onMutate={mutate} />)}</div>
        </details>
      ) : null}

    </main>
  );

  return data ? <AuthenticatedShell session={data.session}>{content}</AuthenticatedShell> : content;
}

function CategoryManagerRow({ category, categories, busy, onMutate }: { category: TransactionReviewView["categories"][number]; categories: TransactionReviewView["categories"]; busy: boolean; onMutate: (url: string, options: RequestInit, message: string) => Promise<Record<string, unknown> | null> }) {
  const [name, setName] = useState(category.name);
  const [kind, setKind] = useState(category.kind);
  const [replacement, setReplacement] = useState("");
  return <div className={styles.categoryRow}><input aria-label={`${category.name} name`} value={name} onChange={(event) => setName(event.target.value)} /><select aria-label={`${category.name} type`} value={kind} onChange={(event) => setKind(event.target.value)}><option value="expense">Expense</option><option value="income">Income</option></select><button type="button" className={styles.secondaryButton} disabled={busy || !name.trim()} onClick={() => void onMutate(`/api/categories/${category.id}`, { method: "PATCH", body: JSON.stringify({ name, kind }) }, "Category updated.")}>Save</button><select aria-label={`${category.name} replacement`} value={replacement} onChange={(event) => setReplacement(event.target.value)}><option value="">Move to Uncategorized</option>{categories.filter((row) => row.id !== category.id).map((row) => <option key={row.id} value={row.id}>Move to {row.name}</option>)}</select><button type="button" className={styles.dangerButton} disabled={busy} onClick={() => window.confirm(`Delete ${category.name}?`) && void onMutate(`/api/categories/${category.id}`, { method: "DELETE", body: JSON.stringify({ replacementCategoryId: replacement ? Number(replacement) : null }) }, "Category removed.")}>Delete</button></div>;
}
