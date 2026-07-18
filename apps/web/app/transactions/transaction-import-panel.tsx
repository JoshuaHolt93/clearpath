"use client";

import type { TransactionImportPreviewView, TransactionReviewView } from "@clearpath/validation";
import { FileSpreadsheet, RefreshCw, Upload } from "lucide-react";
import { ChangeEvent, FormEvent, useState } from "react";

import styles from "./transactions.module.css";

type Mutate = (url: string, options: RequestInit, message: string) => Promise<Record<string, unknown> | null>;

async function responseMessage(response: Response, fallback: string) {
  const body = await response.json().catch(() => null) as { message?: string } | null;
  return body?.message || fallback;
}

export function TransactionImportPanel({ plaidItems, canEdit, busy, onMutate, onImported }: { plaidItems: TransactionReviewView["plaidItems"]; canEdit: boolean; busy: boolean; onMutate: Mutate; onImported: () => void }) {
  const [csvText, setCsvText] = useState("");
  const [fileName, setFileName] = useState("");
  const [preview, setPreview] = useState<TransactionImportPreviewView | null>(null);
  const [fallbackAccount, setFallbackAccount] = useState("Imported Account");
  const [mapping, setMapping] = useState({ date: "", description: "", amount: "", debit: "", credit: "", account: "" });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const readFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setFileName(file.name); setCsvText(await file.text()); setPreview(null); setError("");
  };

  const requestPreview = async (useMapping: boolean) => {
    setLoading(true); setError("");
    try {
      const response = await fetch("/api/transaction-imports/preview", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ csvText, fallbackAccount, mapping: useMapping ? { ...mapping, amount: mapping.amount || null, debit: mapping.debit || null, credit: mapping.credit || null, account: mapping.account || null } : null }) });
      if (!response.ok) throw new Error(await responseMessage(response, "We could not preview that CSV."));
      const next = await response.json() as TransactionImportPreviewView;
      setPreview(next); setMapping({ date: next.mapping.date, description: next.mapping.description, amount: next.mapping.amount ?? "", debit: next.mapping.debit ?? "", credit: next.mapping.credit ?? "", account: next.mapping.account ?? "" });
    } catch (previewError) { setError(previewError instanceof Error ? previewError.message : "We could not preview that CSV."); }
    finally { setLoading(false); }
  };

  const mapSubmit = (event: FormEvent) => { event.preventDefault(); void requestPreview(true); };

  const commit = async () => {
    if (!preview) return;
    const result = await onMutate(`/api/transaction-imports/${preview.stagedImportId}/commit`, { method: "POST", body: "{}" }, `${preview.newCount} transaction${preview.newCount === 1 ? "" : "s"} imported.`);
    if (result) onImported();
  };

  return <section className={styles.importPanel} aria-labelledby="import-title">
    <div className={styles.sectionHeading}><div><h2 id="import-title">Import & Sync</h2><p>Connected institutions and CSV uploads</p></div></div>
    <div className={styles.importGrid}>
      <div className={styles.syncColumn}><h3>Connected Banks</h3>{plaidItems.length ? plaidItems.map((item) => <article key={item.id} className={styles.plaidItem}><div><strong>{item.institutionName || "Connected Institution"}</strong><span>{item.accounts.length} account{item.accounts.length === 1 ? "" : "s"} · {item.status}</span>{item.lastSyncedAt ? <small>Last synced {new Date(item.lastSyncedAt).toLocaleString()}</small> : null}{item.errorMessage ? <small className={styles.inlineError}>{item.errorMessage}</small> : null}</div><button type="button" className={styles.secondaryButton} disabled={!canEdit || busy} onClick={() => void onMutate(`/api/plaid-items/${item.id}/sync`, { method: "POST", body: "{}" }, `${item.institutionName || "Bank"} synced.`)}><RefreshCw size={15} />Sync Now</button></article>) : <div className={styles.empty}>No connected bank accounts.</div>}</div>
      <div className={styles.csvColumn}><h3>CSV File</h3><label className={styles.filePicker}><FileSpreadsheet size={22} aria-hidden="true" /><span>{fileName || "Choose a CSV file"}</span><input type="file" accept=".csv,text/csv" onChange={readFile} disabled={!canEdit} /></label><label>Fallback Account Name<input value={fallbackAccount} onChange={(event) => setFallbackAccount(event.target.value)} /></label><button type="button" className={styles.primaryButton} disabled={!csvText || loading || !canEdit} onClick={() => void requestPreview(false)}><Upload size={16} />{loading ? "Reading..." : "Preview CSV"}</button>{error ? <div className={styles.inlineError} role="alert">{error}</div> : null}</div>
    </div>
    {preview ? <form className={styles.mappingPanel} onSubmit={mapSubmit}><div className={styles.mappingFields}><ColumnSelect label="Date Column" value={mapping.date} headers={preview.headers} required onChange={(value) => setMapping((current) => ({ ...current, date: value }))} /><ColumnSelect label="Description Column" value={mapping.description} headers={preview.headers} required onChange={(value) => setMapping((current) => ({ ...current, description: value }))} /><ColumnSelect label="Amount Column" value={mapping.amount} headers={preview.headers} onChange={(value) => setMapping((current) => ({ ...current, amount: value }))} /><ColumnSelect label="Debit Column" value={mapping.debit} headers={preview.headers} onChange={(value) => setMapping((current) => ({ ...current, debit: value }))} /><ColumnSelect label="Credit Column" value={mapping.credit} headers={preview.headers} onChange={(value) => setMapping((current) => ({ ...current, credit: value }))} /><ColumnSelect label="Account Column" value={mapping.account} headers={preview.headers} onChange={(value) => setMapping((current) => ({ ...current, account: value }))} /></div><div className={styles.mappingActions}><button type="submit" className={styles.secondaryButton} disabled={loading}>Update Preview</button><strong>{preview.newCount} new · {preview.duplicateCount} duplicate{preview.duplicateCount === 1 ? "" : "s"}</strong><button type="button" className={styles.primaryButton} disabled={!preview.newCount || busy} onClick={() => void commit()}>Import {preview.newCount}</button></div><div className={styles.previewTable}><div><strong>Date</strong><strong>Description</strong><strong>Account</strong><strong>Amount</strong></div>{preview.newTransactions.slice(0, 8).map((row, index) => <div key={`${row.postedDate}-${row.description}-${index}`}><span>{row.postedDate}</span><span>{row.description}</span><span>{row.sourceName}</span><strong>{row.amount.toLocaleString(undefined, { style: "currency", currency: "USD" })}</strong></div>)}</div></form> : null}
  </section>;
}

function ColumnSelect({ label, value, headers, required = false, onChange }: { label: string; value: string; headers: string[]; required?: boolean; onChange: (value: string) => void }) {
  return <label>{label}<select value={value} required={required} onChange={(event) => onChange(event.target.value)}><option value="">Not Used</option>{headers.map((header) => <option key={header} value={header}>{header}</option>)}</select></label>;
}
