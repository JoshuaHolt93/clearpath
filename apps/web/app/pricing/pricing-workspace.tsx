"use client";

import { pricingViewSchema, type PricingView } from "@clearpath/validation";
import { Check, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { AuthenticatedShell } from "../authenticated-shell";
import styles from "./pricing.module.css";

async function responseMessage(response: Response, fallback: string) {
  const body = (await response.json().catch(() => null)) as { message?: string } | null;
  return body?.message || fallback;
}

function PricingContent({ data }: { data: PricingView }) {
  const currentPlan = data.session?.selectedPlan ?? null;
  return (
    <div className={styles.page}>
      {!data.session ? (
        <header className={styles.publicHeader}>
          <Link href="/" className={styles.brand}>ClearPath Finance</Link>
          <nav aria-label="Account"><Link href="/login">Sign In</Link><Link href="/register" className={styles.primaryLink}>Create Account</Link></nav>
        </header>
      ) : null}
      <main className={styles.main}>
        <header className={styles.intro}>
          <div><p className={styles.eyebrow}>Plans And Pricing</p><h1>{data.pricingPolicy.title}</h1><p>Choose the planning depth that fits your household. Payment details stay on Stripe-hosted pages.</p><span className={styles.policyMeta}>Version {data.pricingPolicy.version} | Effective {data.pricingPolicy.effectiveDate}</span></div>
          <span className={styles.hostedBadge}><ShieldCheck size={16} aria-hidden="true" />Stripe Hosted</span>
        </header>
        <section className={styles.planGrid} aria-label="Available plans">
          {data.plans.map((plan) => {
            const isCurrent = currentPlan === plan.key;
            return (
              <article key={plan.key} className={`${styles.planCard} ${isCurrent ? styles.currentPlan : ""}`}>
                <div className={styles.planHead}><div><h2>{plan.name}</h2><p>{plan.currency} / {plan.intervalDisplay}</p></div><strong>{plan.priceDisplay}</strong></div>
                {isCurrent ? <span className={styles.currentBadge}>Current Plan</span> : null}
                <ul>
                  {plan.trialPeriodDays ? <li><Check size={15} aria-hidden="true" />First {plan.trialPeriodDays} days are free.</li> : null}
                  {plan.features.map((feature) => <li key={feature}><Check size={15} aria-hidden="true" />{feature}</li>)}
                </ul>
                {data.session?.primaryAccountHolder ? <Link href="/select-plan" className={styles.planAction}>{isCurrent ? "Review Current Plan" : "Choose Plan"}</Link> : data.session ? <p className={styles.accountNote}>The primary account holder manages plan changes.</p> : null}
              </article>
            );
          })}
        </section>
        <section className={styles.terms} aria-labelledby="launch-terms">
          <h2 id="launch-terms">Launch Plan Terms</h2>
          <ul>
            <li>The checkout price is created server-side from ClearPath&apos;s configured Stripe Price IDs.</li>
            {data.plans[0]?.trialPeriodDays ? <li>New subscriptions include a {data.plans[0].trialPeriodDays}-day free trial before recurring billing begins.</li> : null}
            <li>{data.pricingPolicy.cancellationTerms}</li><li>{data.pricingPolicy.paymentCollection}</li>
            <li>ClearPath does not accept browser-submitted price, amount, currency, card number, CVC, or expiration fields.</li>
          </ul>
          <div className={styles.actions}>
            {data.session?.primaryAccountHolder ? <Link href="/select-plan" className={styles.primaryLink}>Choose Or Change Plan</Link> : null}
            {!data.session ? <Link href="/register" className={styles.primaryLink}>Create Account</Link> : null}
            {!data.session ? <Link href="/login" className={styles.secondaryLink}>Sign In</Link> : null}
            <Link href="/security/pci-saq-a" className={styles.secondaryLink}>PCI SAQ-A Controls</Link>
          </div>
        </section>
      </main>
    </div>
  );
}

export function PricingWorkspace() {
  const [data, setData] = useState<PricingView | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const response = await fetch("/api/pricing", { cache: "no-store" });
        if (!response.ok) throw new Error(await responseMessage(response, "We could not load pricing."));
        const parsed = pricingViewSchema.safeParse(await response.json());
        if (!parsed.success) throw new Error("Pricing data did not match the expected contract.");
        if (!cancelled) setData(parsed.data);
      } catch (loadError) {
        if (!cancelled) setError(loadError instanceof Error ? loadError.message : "We could not load pricing.");
      }
    })();
    return () => { cancelled = true; };
  }, []);
  const content = data ? <PricingContent data={data} /> : <main className={styles.state}><p role={error ? "alert" : "status"}>{error || "Loading pricing..."}</p></main>;
  return data?.session ? <AuthenticatedShell session={data.session}>{content}</AuthenticatedShell> : content;
}
