import Link from "next/link";
import type { ReactNode } from "react";

type PendingAuthShellProps = {
  title: string;
  subtitle: string;
  panelTitle: string;
  children: ReactNode;
};

export function PendingAuthShell({
  title,
  subtitle,
  panelTitle,
  children,
}: Readonly<PendingAuthShellProps>) {
  return (
    <div className="pending-auth-page">
      <header className="pending-auth-header">
        <Link href="/" className="pending-brand" aria-label="ClearPath Finance home">
          <span className="logo-mark" aria-hidden="true">C</span>
          <span className="auth-logo-text">
            <span className="name">ClearPath</span>
            <span className="sub">Finance</span>
          </span>
        </Link>
      </header>
      <main className="pending-auth-main">
        <div className="pending-auth-heading">
          <h1>{title}</h1>
          <p>{subtitle}</p>
        </div>
        <section className="pending-auth-panel" aria-labelledby="pending-panel-title">
          <header className="pending-auth-panel-header">
            <h2 id="pending-panel-title">{panelTitle}</h2>
          </header>
          <div className="pending-auth-panel-body">{children}</div>
        </section>
      </main>
    </div>
  );
}
