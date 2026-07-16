import Link from "next/link";
import type { ReactNode } from "react";

type PublicAuthShellProps = {
  children: ReactNode;
  headingId: string;
  subtitle: string;
  title: string;
};

export function PublicAuthShell({ children, headingId, subtitle, title }: PublicAuthShellProps) {
  return (
    <>
      <main className="auth-page">
        <div className="auth-wrap">
          <section className="auth-card" aria-labelledby={headingId}>
            <Link href="/" className="auth-logo" aria-label="ClearPath Finance home">
              <span className="logo-mark" aria-hidden="true">C</span>
              <span className="auth-logo-text">
                <span className="name">ClearPath</span>
                <span className="sub">Finance</span>
              </span>
            </Link>
            <h1 className="auth-title" id={headingId}>{title}</h1>
            <p className="auth-subtitle">{subtitle}</p>
            {children}
          </section>
        </div>
      </main>
      <footer className="public-policy-footer">
        <Link href="/pricing">Pricing</Link>
        <Link href="/privacy">Privacy Policy</Link>
        <Link href="/terms">Terms &amp; Conditions</Link>
        <Link href="/ethics">Ethics Policy</Link>
        <a href="mailto:clearpathfinance1@proton.me">Contact: clearpathfinance1@proton.me</a>
      </footer>
    </>
  );
}
