import type { Metadata } from "next";
import Link from "next/link";

import styles from "./landing.module.css";

export const metadata: Metadata = {
  title: "ClearPath Finance — Budget today. See what's coming next.",
  description:
    "ClearPath Finance helps households organize spending, understand cash flow, and project upcoming balances so money feels less uncertain.",
};

// Landing content ported from Flask templates/landing.html at 92ccdbc
// (hero, "three questions", and feature copy). Web-only static content.

const QUESTIONS = [
  { n: "1", title: "Where am I today?", body: "See your accounts, spending progress, goals, and monthly status in one dashboard." },
  { n: "2", title: "Where is my money going?", body: "Categorize transactions, build budgets, automate cleanup, and understand spending patterns." },
  { n: "3", title: "What will my cash balance look like next?", body: "Project upcoming balances using recurring bills, income schedules, planned expenses, and calendar events." },
];

const FEATURES = [
  { title: "Budget with confidence", body: "Category budgets tied directly to your transactions." },
  { title: "Keep transactions organized", body: "Split purchases, automate categories, and clean up merchants." },
  { title: "Plan ahead", body: "Forecast future cash balances and upcoming expenses." },
  { title: "Manage subscriptions", body: "Detect recurring subscriptions and find cancellation resources." },
];

export default function LandingPage() {
  return (
    <main className={styles.page}>
      <header className={styles.topbar}>
        <span className={styles.brand}>ClearPath Finance</span>
        <nav className={styles.topnav}>
          <Link href="/login">Sign In</Link>
          <Link href="/register" className={styles.cta}>Create Account</Link>
        </nav>
      </header>

      <section className={styles.hero}>
        <h1>Budget today. See what&apos;s coming next.</h1>
        <p className={styles.heroText}>
          ClearPath Finance helps households organize spending, understand cash flow, and project upcoming balances so money feels less uncertain.
        </p>
        <div className={styles.heroActions}>
          <Link href="/register" className={styles.cta}>Create Account</Link>
          <Link href="/login" className={styles.secondary}>Sign In</Link>
        </div>
        <p className={styles.trust}>No investment advice. No financial hype. Just practical household money planning.</p>
      </section>

      <section className={styles.section}>
        <div className={styles.kicker}>Everyday Clarity</div>
        <h2>Three questions every household asks</h2>
        <div className={styles.questionGrid}>
          {QUESTIONS.map((q) => (
            <article key={q.n} className={styles.card}>
              <div className={styles.cardNumber}>{q.n}</div>
              <h3>{q.title}</h3>
              <p>{q.body}</p>
            </article>
          ))}
        </div>
      </section>

      <section className={styles.section}>
        <div className={styles.kicker}>Practical Tools</div>
        <h2>Designed for real household finances</h2>
        <p className={styles.sectionLede}>
          ClearPath keeps the core workflow close to what households actually do: clean up transactions, build budgets, watch progress, and look ahead before a tight month surprises you.
        </p>
        <div className={styles.featureGrid}>
          {FEATURES.map((f) => (
            <article key={f.title} className={styles.card}>
              <h3>{f.title}</h3>
              <p>{f.body}</p>
            </article>
          ))}
        </div>
      </section>

      <section className={styles.finalCta}>
        <h2>Built for Main Street, not Wall Street</h2>
        <p>Start with practical visibility. Upgrade when you want to plan farther ahead.</p>
        <div className={styles.heroActions}>
          <Link href="/register" className={styles.cta}>Create Account</Link>
          <Link href="/login" className={styles.secondary}>Sign In</Link>
        </div>
      </section>

      <footer className={styles.footer}>
        <span>© ClearPath Finance</span>
        <nav>
          <Link href="/privacy">Privacy</Link>
          <Link href="/terms">Terms</Link>
          <Link href="/ethics">Ethics</Link>
        </nav>
      </footer>
    </main>
  );
}
