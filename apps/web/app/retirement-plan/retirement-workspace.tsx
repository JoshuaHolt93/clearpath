"use client";

import { retirementViewSchema, type RetirementView } from "@clearpath/validation";
import { Landmark, RefreshCw } from "lucide-react";
import { FormEvent, useCallback, useEffect, useState } from "react";

import { AuthenticatedPageFrame } from "../authenticated-shell";
import styles from "./retirement.module.css";

const currency = (value: number) => new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(value);

async function responseMessage(response: Response, fallback: string) {
  const body = (await response.json().catch(() => null)) as { message?: string } | null;
  return body?.message || fallback;
}

function numberValue(value: FormDataEntryValue | null) {
  const raw = String(value ?? "").replaceAll(",", "").trim();
  const parsed = Number(raw || "0");
  return Number.isFinite(parsed) ? Math.max(parsed, 0) : 0;
}

type NotesKey =
  | "retirementLifestyleNotes"
  | "retirementLocationNotes"
  | "retirementHealthcareNotes"
  | "retirementIncomeNotes"
  | "retirementDebtNotes"
  | "retirementFamilyNotes";

const WORKSHEET_FIELDS: { name: string; label: string; key: NotesKey }[] = [
  { name: "retirementLifestyleNotes", label: "Lifestyle", key: "retirementLifestyleNotes" },
  { name: "retirementLocationNotes", label: "Location", key: "retirementLocationNotes" },
  { name: "retirementHealthcareNotes", label: "Healthcare", key: "retirementHealthcareNotes" },
  { name: "retirementIncomeNotes", label: "Income", key: "retirementIncomeNotes" },
  { name: "retirementDebtNotes", label: "Debt", key: "retirementDebtNotes" },
  { name: "retirementFamilyNotes", label: "Family", key: "retirementFamilyNotes" },
];

export function RetirementWorkspace() {
  const [data, setData] = useState<RetirementView | null>(null);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setError("");
    try {
      const response = await fetch("/api/retirement-plan", { cache: "no-store" });
      if (!response.ok) throw new Error(await responseMessage(response, "We could not load your retirement plan."));
      const parsed = retirementViewSchema.safeParse(await response.json());
      if (!parsed.success) throw new Error("Retirement data did not match the expected contract.");
      setData(parsed.data);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "We could not load your retirement plan.");
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const canEdit = Boolean(data && (data.session.primaryAccountHolder || data.session.subject.householdRole !== "viewer"));

  const patch = async (payload: Record<string, unknown>, success: string) => {
    setBusy(true);
    setStatus("");
    setError("");
    try {
      const response = await fetch("/api/retirement-plan", {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) throw new Error(await responseMessage(response, "We could not save your changes."));
      const parsed = retirementViewSchema.safeParse(await response.json());
      if (!parsed.success) throw new Error("Retirement data did not match the expected contract.");
      setData(parsed.data);
      setStatus(success);
    } catch (patchError) {
      setError(patchError instanceof Error ? patchError.message : "We could not save your changes.");
    } finally {
      setBusy(false);
    }
  };

  const submitSurvey = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    await patch(
      {
        section: "survey",
        retirementEnabled: values.get("retirement_enabled") === "1",
        retirementHasEmployerPlan: values.get("retirement_has_employer_plan") === "1",
        retirementEmployerWithheld: values.get("retirement_employer_withheld") === "1",
        retirementHasPersonalPlan: values.get("retirement_has_personal_plan") === "1",
        retirementMonthlyContribution: numberValue(values.get("retirement_monthly_contribution")),
        retirementPersonalMonthlyContribution: numberValue(values.get("retirement_personal_monthly_contribution")),
      },
      "Retirement plan updated.",
    );
  };

  const submitWorksheet = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    await patch(
      {
        section: "worksheet",
        retirementLifestyleNotes: String(values.get("retirementLifestyleNotes") ?? "").trim(),
        retirementLocationNotes: String(values.get("retirementLocationNotes") ?? "").trim(),
        retirementHealthcareNotes: String(values.get("retirementHealthcareNotes") ?? "").trim(),
        retirementIncomeNotes: String(values.get("retirementIncomeNotes") ?? "").trim(),
        retirementDebtNotes: String(values.get("retirementDebtNotes") ?? "").trim(),
        retirementFamilyNotes: String(values.get("retirementFamilyNotes") ?? "").trim(),
      },
      "Retirement worksheet saved.",
    );
  };

  const content = (
    <div className={styles.layout}>
      <header className={styles.header}>
        <div className={styles.title}><Landmark size={20} aria-hidden="true" /><div><h1>Retirement Planning</h1><p>Educational planning for long-term goals. This is not investment advice.</p></div></div>
        <button type="button" onClick={() => void load()} disabled={busy}><RefreshCw size={16} aria-hidden="true" />Refresh</button>
      </header>

      {error ? <p role="alert" className={styles.error}>{error}</p> : null}
      {status ? <p role="status" className={styles.status}>{status}</p> : null}
      {!data && !error ? <p className={styles.loading}>Loading retirement plan...</p> : null}

      {data ? (
        <div className={styles.sections}>
          <section className={styles.panel}>
            <h2>Monthly Retirement Contribution</h2>
            <p className={styles.figure}>{currency(data.retirementContribution)}<span> / month toward retirement in your cash-flow plan</span></p>
            <form key={`survey-${data.profile.retirementEnabled}`} onSubmit={(event) => void submitSurvey(event)}>
              <label className={styles.checkboxRow}><input type="checkbox" name="retirement_enabled" value="1" defaultChecked={data.profile.retirementEnabled} disabled={!canEdit || busy} />Include retirement contributions in my plan</label>
              <label className={styles.checkboxRow}><input type="checkbox" name="retirement_has_employer_plan" value="1" defaultChecked={data.profile.retirementHasEmployerPlan} disabled={!canEdit || busy} />I have an employer retirement plan</label>
              <label className={styles.checkboxRow}><input type="checkbox" name="retirement_employer_withheld" value="1" defaultChecked={data.profile.retirementEmployerWithheld} disabled={!canEdit || busy} />Employer contributions are withheld from my paycheck</label>
              <label className={styles.checkboxRow}><input type="checkbox" name="retirement_has_personal_plan" value="1" defaultChecked={data.profile.retirementHasPersonalPlan} disabled={!canEdit || busy} />I have a personal retirement plan</label>
              <div className={styles.formGrid}>
                <label>Employer Monthly Contribution<input name="retirement_monthly_contribution" type="number" min="0" step="0.01" defaultValue={data.profile.retirementMonthlyContribution} disabled={!canEdit || busy} /></label>
                <label>Personal Monthly Contribution<input name="retirement_personal_monthly_contribution" type="number" min="0" step="0.01" defaultValue={data.profile.retirementPersonalMonthlyContribution} disabled={!canEdit || busy} /></label>
              </div>
              <button type="submit" disabled={!canEdit || busy}>Save Retirement Plan</button>
            </form>
          </section>

          <section className={styles.panel}>
            <h2>Planning Worksheet</h2>
            <p className={styles.meta}>Capture the considerations that matter for your retirement picture. These notes are private to your household.</p>
            <form key={`worksheet-${data.profile.retirementLifestyleNotes ?? ""}`} onSubmit={(event) => void submitWorksheet(event)}>
              <div className={styles.worksheetGrid}>
                {WORKSHEET_FIELDS.map((field) => (
                  <label key={field.name}>{field.label}
                    <textarea name={field.name} rows={3} defaultValue={data.profile[field.key] ?? ""} disabled={!canEdit || busy} />
                  </label>
                ))}
              </div>
              <button type="submit" disabled={!canEdit || busy}>Save Worksheet</button>
            </form>
          </section>

          <section className={styles.panel}>
            <h2>Retirement Accounts</h2>
            {data.accounts.length === 0 ? (
              <p className={styles.meta}>No retirement accounts are linked yet. Connect accounts from Settings to see balances here.</p>
            ) : (
              <ul className={styles.accounts}>
                {data.accounts.map((account) => (
                  <li key={account.id}>
                    <span>{account.name}{account.institution ? ` — ${account.institution}` : ""}</span>
                    <strong>{currency(account.currentBalance)}</strong>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      ) : null}
    </div>
  );

  return <AuthenticatedPageFrame session={data?.session}>{content}</AuthenticatedPageFrame>;
}
