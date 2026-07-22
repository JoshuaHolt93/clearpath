"use client";

import { billingViewSchema, type BillingPlan, type BillingView } from "@clearpath/validation";
import { CreditCard, ExternalLink, RefreshCw, ShieldCheck } from "lucide-react";
import { FormEvent, useCallback, useEffect, useState } from "react";

import { AuthenticatedPageFrame } from "../authenticated-shell";
import styles from "./billing.module.css";

async function responseMessage(response: Response, fallback: string) {
  const body = (await response.json().catch(() => null)) as { message?: string } | null;
  return body?.message || fallback;
}

function selectLabel(plan: BillingPlan, currentPlan: string | null): string {
  if (!currentPlan) return `Select ${plan.name.replace("ClearPath ", "")}`;
  if (currentPlan === plan.key) return "Current Plan";
  if (plan.key === "premium") return "Upgrade to Premier";
  if (plan.key === "basic" && currentPlan === "premium") return "Switch to Plus";
  if (plan.key === "basic") return "Upgrade to Plus";
  if (plan.key === "at_cost") return "Switch to Basic";
  return "Choose Plan";
}

export function BillingWorkspace() {
  const [data, setData] = useState<BillingView | null>(null);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const [cancelOpen, setCancelOpen] = useState(false);

  const load = useCallback(async () => {
    setError("");
    try {
      const response = await fetch("/api/billing", { cache: "no-store" });
      if (!response.ok) throw new Error(await responseMessage(response, "We could not load billing."));
      const parsed = billingViewSchema.safeParse(await response.json());
      if (!parsed.success) throw new Error("Billing data did not match the expected contract.");
      setData(parsed.data);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "We could not load billing.");
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const currentPlan = data?.userState?.selectedPlan ?? data?.session.selectedPlan ?? null;
  const billingEnabled = Boolean(data?.billingConfig?.enabled);

  const selectPlan = async (event: FormEvent<HTMLFormElement>, planKey: string) => {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    setBusy(true);
    setStatus("");
    setError("");
    try {
      const response = await fetch("/api/billing/plan-selection", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ plan: planKey, promotionCode: String(values.get("promotion_code") ?? "").trim() || null }),
      });
      const body = (await response.json().catch(() => null)) as { message?: string; checkoutUrl?: string | null; alreadySelected?: boolean; planName?: string } | null;
      if (!response.ok) throw new Error(body?.message || "We could not update your plan.");
      if (body?.checkoutUrl) {
        // Stripe-hosted Checkout: the client performs the handoff.
        window.location.assign(body.checkoutUrl);
        return;
      }
      setStatus(body?.alreadySelected ? `You're staying on ${body.planName}.` : `${body?.planName} selected.`);
      await load();
    } catch (selectError) {
      setError(selectError instanceof Error ? selectError.message : "We could not update your plan.");
    } finally {
      setBusy(false);
    }
  };

  const openPortal = async () => {
    setBusy(true);
    setError("");
    try {
      const response = await fetch("/api/billing/portal", { method: "POST" });
      const body = (await response.json().catch(() => null)) as { message?: string; portalUrl?: string } | null;
      if (!response.ok || !body?.portalUrl) throw new Error(body?.message || "We could not open the billing portal.");
      window.location.assign(body.portalUrl);
    } catch (portalError) {
      setError(portalError instanceof Error ? portalError.message : "We could not open the billing portal.");
      setBusy(false);
    }
  };

  const submitCancel = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    setBusy(true);
    setStatus("");
    setError("");
    try {
      const response = await fetch("/api/billing/cancel", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          reason: String(values.get("reason") ?? "").trim() || null,
          description: String(values.get("description") ?? "").trim() || null,
        }),
      });
      const body = (await response.json().catch(() => null)) as { message?: string; portalUrl?: string | null } | null;
      if (!response.ok) throw new Error(body?.message || "We could not start cancellation.");
      if (body?.portalUrl) {
        window.location.assign(body.portalUrl);
        return;
      }
      setStatus(body?.message || "Your feedback was saved.");
      setCancelOpen(false);
      await load();
    } catch (cancelError) {
      setError(cancelError instanceof Error ? cancelError.message : "We could not start cancellation.");
    } finally {
      setBusy(false);
    }
  };

  const content = (
    <div className={styles.layout}>
      <header className={styles.header}>
        <div>
          <h1>Billing And Plans</h1>
          <p>Choose the ClearPath experience you want. Payment details are entered only on Stripe-hosted pages.</p>
        </div>
        <button type="button" onClick={() => void load()} disabled={busy}><RefreshCw size={16} aria-hidden="true" />Refresh</button>
      </header>

      {error ? <p role="alert" className={styles.error}>{error}</p> : null}
      {status ? <p role="status" className={styles.status}>{status}</p> : null}
      {!data && !error ? <p className={styles.loading}>Loading billing...</p> : null}

      {data ? (
        <>
          {!data.canManageBilling ? (
            <p className={styles.meta}>Billing is managed by the primary account holder. You can review the available plans below.</p>
          ) : null}

          <div className={styles.planGrid}>
            {data.plans.map((plan) => {
              const isCurrent = currentPlan === plan.key;
              return (
                <form key={plan.key} className={`${styles.planCard} ${isCurrent ? styles.currentPlan : ""}`} onSubmit={(event) => void selectPlan(event, plan.key)} aria-current={isCurrent ? "true" : undefined}>
                  <div className={styles.planHead}>
                    <div>
                      <div className={styles.planName}>{plan.name}</div>
                      <div className={styles.meta}>{plan.currency} / {plan.intervalDisplay}</div>
                    </div>
                    <div className={styles.priceWrap}>
                      {isCurrent ? <span className={styles.badge}>Current Plan</span> : null}
                      <div className={styles.price}>{plan.priceDisplay}</div>
                    </div>
                  </div>
                  <ul className={styles.features}>
                    {plan.trialPeriodDays ? <li>First {plan.trialPeriodDays} days are free; billing starts after the trial.</li> : null}
                    {plan.features.map((feature) => <li key={feature}>{feature}</li>)}
                  </ul>
                  {data.canManageBilling ? (
                    <>
                      <label className={styles.promo}>Promo Code (Optional)
                        <input name="promotion_code" maxLength={80} autoComplete="off" spellCheck={false} placeholder="Enter promo code" disabled={busy || isCurrent} />
                      </label>
                      <button type="submit" disabled={busy || isCurrent}>{selectLabel(plan, currentPlan)}</button>
                    </>
                  ) : null}
                </form>
              );
            })}
          </div>

          <section className={styles.secure}>
            <ShieldCheck size={18} aria-hidden="true" />
            <p>{billingEnabled ? "Payment details are entered only on Stripe-hosted pages." : "Billing is not enabled in this environment, so a selected plan is saved without opening Stripe Checkout."}</p>
          </section>

          {data.canManageBilling && data.userState ? (
            <section className={styles.manage} aria-labelledby="billing-manage">
              <header><CreditCard size={18} aria-hidden="true" /><h2 id="billing-manage">Manage Subscription</h2></header>
              <p className={styles.meta}>Status: {data.userState.billingStatus}. Plan: {data.session.planDisplayName}.</p>
              {data.userState.hasStripeCustomer ? (
                <div className={styles.manageActions}>
                  <button type="button" onClick={() => void openPortal()} disabled={busy}><ExternalLink size={16} aria-hidden="true" />Open Billing Portal</button>
                  {data.userState.hasStripeSubscription ? (
                    <button type="button" className={styles.dangerButton} onClick={() => setCancelOpen((open) => !open)} disabled={busy}>Cancel Subscription</button>
                  ) : null}
                </div>
              ) : (
                <p className={styles.meta}>No Stripe customer is connected to this account yet.</p>
              )}

              {cancelOpen ? (
                <form className={styles.cancelForm} onSubmit={(event) => void submitCancel(event)}>
                  <p className={styles.meta}>ClearPath records this feedback, then opens Stripe Billing Portal. The subscription is canceled only after you confirm on Stripe-hosted pages.</p>
                  <label>Reason (Optional)
                    <select name="reason" defaultValue="" disabled={busy}>
                      <option value="">Prefer not to say</option>
                      {(data.feedbackOptions?.reasons ?? []).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                    </select>
                  </label>
                  <label>Anything else? (Optional)
                    <textarea name="description" rows={3} disabled={busy} />
                  </label>
                  <button type="submit" disabled={busy}>Continue To Stripe Cancellation</button>
                </form>
              ) : null}
            </section>
          ) : null}
        </>
      ) : null}
    </div>
  );

  return <AuthenticatedPageFrame session={data?.session}>{content}</AuthenticatedPageFrame>;
}
