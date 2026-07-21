"use client";

import { complianceViewSchema, type ComplianceView } from "@clearpath/validation";
import { RefreshCw, ShieldAlert } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { AuthenticatedShell } from "../authenticated-shell";
import styles from "./compliance.module.css";

async function responseMessage(response: Response, fallback: string) {
  const body = (await response.json().catch(() => null)) as { message?: string } | null;
  return body?.message || fallback;
}

const STATUS_LABEL: Record<string, string> = { pass: "Pass", warn: "Warn", fail: "Fail" };

export function ComplianceWorkspace() {
  const [data, setData] = useState<ComplianceView | null>(null);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setError("");
    try {
      const response = await fetch("/api/compliance", { cache: "no-store" });
      if (!response.ok) throw new Error(await responseMessage(response, "We could not load compliance data."));
      const parsed = complianceViewSchema.safeParse(await response.json());
      if (!parsed.success) throw new Error("Compliance data did not match the expected contract.");
      setData(parsed.data);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "We could not load compliance data.");
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const runEvaluations = async () => {
    setBusy(true);
    setStatus("");
    setError("");
    try {
      const response = await fetch("/api/compliance", { method: "POST" });
      const body = (await response.json().catch(() => null)) as { message?: string } | null;
      if (!response.ok) throw new Error(body?.message || "We could not run the control evaluations.");
      setStatus(body?.message || "Control evaluations recorded.");
      await load();
    } catch (runError) {
      setError(runError instanceof Error ? runError.message : "We could not run the control evaluations.");
    } finally {
      setBusy(false);
    }
  };

  const content = (
    <div className={styles.layout}>
      <header className={styles.header}>
        <div>
          <h1>Compliance Controls</h1>
          <p>SOC2 CC4.1 control evaluations and evidence.</p>
        </div>
        {data?.isAdmin ? (
          <div className={styles.actions}>
            <button type="button" onClick={() => void load()} disabled={busy}><RefreshCw size={16} aria-hidden="true" />Refresh</button>
            <button type="button" onClick={() => void runEvaluations()} disabled={busy}>Run Evaluations</button>
          </div>
        ) : null}
      </header>

      {error ? <p role="alert" className={styles.error}>{error}</p> : null}
      {status ? <p role="status" className={styles.statusMsg}>{status}</p> : null}
      {!data && !error ? <p className={styles.loading}>Loading compliance data...</p> : null}

      {data && !data.isAdmin ? (
        <div className={styles.denied}>
          <ShieldAlert size={20} aria-hidden="true" />
          <p>Administrator access is required to view compliance control evaluations.</p>
        </div>
      ) : null}

      {data?.isAdmin ? (
        <>
          <section className={styles.panel}>
            <h2>Latest Evaluations</h2>
            {data.evaluations.length === 0 ? (
              <p className={styles.meta}>No evaluations recorded yet. Run the evaluations to capture current control evidence.</p>
            ) : (
              <div className={styles.tableScroll}>
                <table className={styles.table}>
                  <thead><tr><th>Control</th><th>Status</th><th>Evidence</th><th>Evaluated</th></tr></thead>
                  <tbody>
                    {data.evaluations.map((row) => (
                      <tr key={row.id}>
                        <td>{row.controlName}<span className={styles.controlId}>{row.controlId}</span></td>
                        <td><span className={`${styles.status} ${styles[row.status]}`}>{STATUS_LABEL[row.status]}</span></td>
                        <td>{row.evidence}</td>
                        <td>{new Date(row.evaluatedAt).toLocaleString("en-US")}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section className={styles.panel}>
            <h2>Control Catalog</h2>
            <ul className={styles.catalog}>
              {data.controls.map((control) => (
                <li key={control.id}>
                  <strong>{control.name}</strong> <span className={styles.controlId}>{control.id}</span>
                  <p className={styles.meta}>{control.description}</p>
                </li>
              ))}
            </ul>
          </section>
        </>
      ) : null}
    </div>
  );

  return data ? <AuthenticatedShell session={data.session}>{content}</AuthenticatedShell> : content;
}
