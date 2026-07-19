"use client";

import { loanPlanDetailSchema, loanPlanResourceSchema, type LoanPlanDetail, type LoanPlanResource } from "@clearpath/validation";
import { ArrowLeft, Check, RefreshCw, Save } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FormEvent, useCallback, useEffect, useState } from "react";

import { AuthenticatedShell } from "../../authenticated-shell";
import styles from "../loan-plans.module.css";

const currency = (value: number) => new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value);
async function responseMessage(response: Response, fallback: string) { const body = await response.json().catch(() => null) as { message?: string } | null; return body?.message || fallback; }
function canEdit(data: LoanPlanDetail) { return data.session.primaryAccountHolder || data.session.subject.householdRole !== "viewer"; }

export function LoanPlanWorkspace({ itemId }: { itemId: string }) {
  const router = useRouter();
  const [data, setData] = useState<LoanPlanDetail | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      const response = await fetch(`/api/loan-plans/${itemId}`, { cache: "no-store" });
      if (response.status === 403) { router.replace("/select-plan"); return; }
      if (!response.ok) throw new Error(await responseMessage(response, "We could not load that loan plan."));
      const parsed = loanPlanDetailSchema.safeParse(await response.json());
      if (!parsed.success) throw new Error("Loan plan data did not match the expected contract.");
      setData(parsed.data);
    } catch (loadError) { setError(loadError instanceof Error ? loadError.message : "We could not load that loan plan."); }
  }, [itemId, router]);

  useEffect(() => { void load(); }, [load]);

  const apply = (payload: unknown) => {
    const parsed = loanPlanResourceSchema.safeParse(payload);
    if (!parsed.success) throw new Error("Loan plan data did not match the expected contract.");
    setData((current) => current ? { ...current, resource: parsed.data } : current);
  };

  const save = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!data) return;
    const form = new FormData(event.currentTarget);
    const payload = { principalBalance: Number(form.get("principalBalance") ?? 0), collateralValue: Number(form.get("collateralValue") ?? 0), annualInterestRate: Number(form.get("annualInterestRate") ?? 0), termValue: Number(form.get("termValue") ?? 0), termUnit: String(form.get("termUnit") ?? "months"), regularPayment: Number(form.get("regularPayment") ?? 0), extraPaymentOne: Number(form.get("extraPaymentOne") ?? 0), extraPaymentTwo: Number(form.get("extraPaymentTwo") ?? 0), selectedScenario: data.resource.plan?.selectedScenario ?? "base", notes: String(form.get("notes") ?? "").trim() || null };
    setBusy("save"); setError(""); setNotice("");
    try {
      const response = await fetch(`/api/loan-plans/${itemId}`, { method: "PATCH", headers: { "content-type": "application/json" }, body: JSON.stringify(payload) });
      if (!response.ok) throw new Error(await responseMessage(response, "We could not save that loan plan."));
      apply(await response.json()); setNotice("Amortization schedule updated.");
    } catch (saveError) { setError(saveError instanceof Error ? saveError.message : "We could not save that loan plan."); } finally { setBusy(""); }
  };

  const selectScenario = async (selectedScenario: string) => {
    setBusy(`scenario-${selectedScenario}`); setError(""); setNotice("");
    try {
      const response = await fetch(`/api/loan-plans/${itemId}/selected-scenario`, { method: "PATCH", headers: { "content-type": "application/json" }, body: JSON.stringify({ selectedScenario }) });
      if (!response.ok) throw new Error(await responseMessage(response, "We could not select that payoff plan."));
      apply(await response.json()); setNotice("Selected payoff plan updated.");
    } catch (selectError) { setError(selectError instanceof Error ? selectError.message : "We could not select that payoff plan."); } finally { setBusy(""); }
  };

  const resource = data?.resource;
  const plan = resource?.plan;
  const termUnit = plan?.termUnitPreference === "years" ? "years" : "months";
  const termValue = plan ? (termUnit === "years" ? plan.termMonths / 12 : plan.termMonths) : 360;
  const kindLabel = resource?.loanKind === "mortgage" ? "Mortgage" : "Loan";
  const formKey = plan ? `${plan.principalBalance}-${plan.termMonths}-${plan.selectedScenario}-${plan.regularPayment}-${plan.extraPaymentOne}-${plan.extraPaymentTwo}` : "new";

  const content = <main className={styles.page}>
    <header className={styles.pageHeader}><div><p className={styles.eyebrow}>{kindLabel} Schedule</p><h1>{kindLabel} Planning Tool</h1><p>{resource ? `${resource.fixedExpense.name} - compare payoff scenarios and review the full amortization schedule.` : "Loading amortization details."}</p></div><Link className={styles.backLink} href="/loan-plans"><ArrowLeft size={15} aria-hidden="true" />Back To Mortgage/Loan Planning</Link></header>
    {error ? <div className={styles.error} role="alert"><span>{error}</span>{!data ? <button type="button" onClick={() => void load()}>Try Again</button> : null}</div> : null}
    {notice ? <div className={styles.notice} role="status">{notice}</div> : null}
    {!data && !error ? <div className={styles.loading}><RefreshCw className={styles.spin} size={20} />Loading amortization schedule...</div> : null}
    {data && resource ? <div className={styles.content}>
      {!canEdit(data) ? <div className={styles.viewerNotice}>You can review assumptions, comparisons, and the full schedule. An owner or editor can save details or select a payoff plan.</div> : null}
      <section className={styles.detailGrid}>
        <article className={styles.panel}><header><div><h2>{kindLabel} Details</h2><p>Stored assumptions used by the server amortization engine.</p></div></header><form className={styles.loanForm} key={formKey} onSubmit={(event) => void save(event)}><div className={styles.formGrid}><label>Principal Balance<input name="principalBalance" type="number" min="0" step="0.01" defaultValue={plan?.principalBalance ?? 0} disabled={!canEdit(data) || Boolean(busy)} /></label><label>{resource.loanKind === "mortgage" ? "Home/Property Value" : "Asset Value For Net Worth"}<input name="collateralValue" type="number" min="0" step="0.01" defaultValue={plan?.collateralValue ?? 0} disabled={!canEdit(data) || Boolean(busy)} /></label></div><div className={styles.formGridThree}><label>Interest Rate<input name="annualInterestRate" type="number" min="0" step="0.001" defaultValue={plan?.annualInterestRate ?? 0} disabled={!canEdit(data) || Boolean(busy)} /></label><label>Remaining Term<span className={styles.termRow}><input aria-label="Remaining Term" name="termValue" type="number" min="0.25" step="0.25" defaultValue={termValue} disabled={!canEdit(data) || Boolean(busy)} /><select aria-label="Term Unit" name="termUnit" defaultValue={termUnit} disabled={!canEdit(data) || Boolean(busy)}><option value="months">Months</option><option value="years">Years</option></select></span></label><label>Regular Monthly Payment<input name="regularPayment" type="number" min="0" step="0.01" defaultValue={plan?.regularPayment ?? resource.fixedExpense.amount} disabled={!canEdit(data) || Boolean(busy)} /></label></div><div className={styles.formGrid}><label>Extra Payment Scenario 1<input name="extraPaymentOne" type="number" min="0" step="0.01" defaultValue={plan?.extraPaymentOne ?? 0} disabled={!canEdit(data) || Boolean(busy)} /></label><label>Extra Payment Scenario 2<input name="extraPaymentTwo" type="number" min="0" step="0.01" defaultValue={plan?.extraPaymentTwo ?? 0} disabled={!canEdit(data) || Boolean(busy)} /></label></div><label>Notes<input name="notes" defaultValue={plan?.notes ?? ""} disabled={!canEdit(data) || Boolean(busy)} placeholder="Optional" /></label><button type="submit" disabled={!canEdit(data) || Boolean(busy)}><Save size={16} aria-hidden="true" />{busy === "save" ? "Saving..." : "Save Loan Details"}</button></form></article>
        <article className={styles.panel}><header><div><h2>Scenario Comparison</h2><p>Server-calculated payoff timing and interest.</p></div></header>{resource.scenarios.length ? <><div className={styles.tableWrap}><table><thead><tr><th>Scenario</th><th>Extra</th><th>Payoff</th><th>Interest</th><th>Payoff Plan</th></tr></thead><tbody>{resource.scenarios.map((scenario) => <tr key={scenario.key}><td>{scenario.label}</td><td>{currency(scenario.extraPayment)}</td><td>{scenario.months} Months</td><td>{currency(scenario.interestPaid)}</td><td>{plan?.selectedScenario === scenario.key ? <span className={styles.selected}><Check size={12} aria-hidden="true" />Selected</span> : <button type="button" className={styles.selectButton} disabled={!canEdit(data) || Boolean(busy)} onClick={() => void selectScenario(scenario.key)}>{busy === `scenario-${scenario.key}` ? "Selecting..." : "Select"}</button>}</td></tr>)}</tbody></table></div><div className={styles.callout}>The selected payoff plan feeds its extra monthly principal payment into the Budgets Debt Paydown Target and cash-flow calculations.</div></> : <div className={styles.empty}><strong>Save loan details first</strong><p>ClearPath will calculate the scenario comparison and full amortization schedule.</p></div>}</article>
      </section>
      <section className={styles.panel}><header><div><h2>Full Amortization Schedule</h2><p>{plan ? `${plan.selectedScenario.replaceAll("_", " ")} selected` : "Enter loan assumptions to generate the schedule."}</p></div></header>{resource.selectedSchedule.length ? <div className={styles.tableWrap}><table className={styles.scheduleTable}><thead><tr><th>Month</th><th>Date</th><th>Beginning Balance</th><th>Payment</th><th>Principal</th><th>Interest</th><th>Ending Balance</th></tr></thead><tbody>{resource.selectedSchedule.map((row) => <tr key={row.month}><td>{row.month}</td><td>{new Date(`${row.paymentDate}T12:00:00`).toLocaleDateString("en-US")}</td><td>{currency(row.beginningBalance)}</td><td>{currency(row.payment)}</td><td>{currency(row.principal)}</td><td>{currency(row.interest)}</td><td>{currency(row.endingBalance)}</td></tr>)}</tbody></table></div> : <div className={styles.empty}><strong>No amortization schedule yet</strong><p>Enter principal, interest rate, term, and monthly payment to generate the full schedule.</p></div>}</section>
    </div> : null}
  </main>;
  return data ? <AuthenticatedShell session={data.session}>{content}</AuthenticatedShell> : content;
}
