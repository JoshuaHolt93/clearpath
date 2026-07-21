import Link from "next/link";

import type { LegalPolicy } from "@/lib/legal-content";
import styles from "./legal.module.css";

export function PolicyView({ policy }: { policy: LegalPolicy }) {
  return (
    <main className={styles.page}>
      <div className={styles.card}>
        <header className={styles.header}>
          <Link href="/" className={styles.brand}>ClearPath Finance</Link>
          <h1>{policy.title}</h1>
          <p className={styles.meta}>Version {policy.version} · Effective {policy.effectiveDate}</p>
          {policy.owner ? <p className={styles.meta}>Owner: {policy.owner}</p> : null}
          {policy.reviewCadence ? <p className={styles.meta}>{policy.reviewCadence}</p> : null}
        </header>
        {policy.intro ? <p className={styles.intro}>{policy.intro}</p> : null}
        {policy.scope ? <p className={styles.intro}>{policy.scope}</p> : null}
        {policy.note ? <p className={styles.contact}>{policy.note}</p> : null}
        {policy.contact ? <p className={styles.contact}>{policy.contact}</p> : null}
        <div className={styles.sections}>
          {policy.sections.map((section) => (
            <section key={section.heading}>
              <h2>{section.heading}</h2>
              {section.summary ? <p className={styles.summary}>{section.summary}</p> : null}
              <ul>
                {section.items.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </section>
          ))}
        </div>
        <footer className={styles.footer}>
          <Link href="/privacy">Privacy Policy</Link>
          <Link href="/terms">Terms Of Service</Link>
          <Link href="/login">Sign In</Link>
        </footer>
      </div>
    </main>
  );
}
