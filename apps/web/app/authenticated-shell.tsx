"use client";

import type { DashboardView } from "@clearpath/validation";
import {
  BarChart3,
  CalendarRange,
  ChevronDown,
  CircleHelp,
  Goal,
  Home,
  Landmark,
  LogOut,
  Menu,
  MessageSquareText,
  PiggyBank,
  ReceiptText,
  Settings,
  Sparkles,
  X,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { type ReactNode, useMemo, useState } from "react";

import styles from "./authenticated-shell.module.css";

type Session = DashboardView["session"];

type AuthenticatedShellProps = {
  session: Session;
  children: ReactNode;
};

function featureEnabled(session: Session, key: string): boolean {
  return session.featureAccess.some((row) => row.feature === key && row.enabled && !row.hidden);
}

function NavLink({ href, label, icon, active, compact = false, onNavigate }: {
  href: string;
  label: string;
  icon?: ReactNode;
  active: boolean;
  compact?: boolean;
  onNavigate(): void;
}) {
  return (
    <Link href={href} className={`${compact ? styles.subLink : styles.navLink} ${active ? styles.active : ""}`} onClick={onNavigate}>
      {icon}<span>{label}</span>
    </Link>
  );
}

export function AuthenticatedShell({ session, children }: AuthenticatedShellProps) {
  const pathname = usePathname();
  const router = useRouter();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [planOpen, setPlanOpen] = useState(pathname.startsWith("/monthly-plan") || pathname.startsWith("/cash-projections"));
  const [reviewOpen, setReviewOpen] = useState(pathname.startsWith("/transactions") || pathname.startsWith("/subscriptions") || pathname.startsWith("/category-rules"));
  const [signingOut, setSigningOut] = useState(false);
  const visibleFeatures = useMemo(() => new Set(
    session.featureAccess.filter((row) => row.enabled && !row.hidden).map((row) => row.feature),
  ), [session.featureAccess]);
  const closeMobile = () => setMobileOpen(false);

  const signOut = async () => {
    setSigningOut(true);
    await fetch("/api/auth/session", { method: "DELETE" }).catch(() => undefined);
    router.replace("/login");
    router.refresh();
  };

  return (
    <div className={styles.frame}>
      <header className={styles.mobileHeader}>
        <button type="button" className={styles.iconButton} aria-label="Open navigation" title="Open navigation" onClick={() => setMobileOpen(true)}>
          <Menu size={21} aria-hidden="true" />
        </button>
        <Link href="/dashboard" className={styles.mobileBrand} onClick={closeMobile}>
          <span className="logo-mark">C</span><strong>ClearPath</strong>
        </Link>
        <span className={styles.mobileAvatar}>{session.subject.avatarInitial}</span>
      </header>

      {mobileOpen ? <button type="button" className={styles.backdrop} aria-label="Close navigation" onClick={closeMobile} /> : null}
      <aside className={`${styles.sidebar} ${mobileOpen ? styles.sidebarOpen : ""}`}>
        <div className={styles.brandRow}>
          <Link href="/dashboard" className={styles.brand} onClick={closeMobile}>
            <span className="logo-mark">C</span>
            <span><strong>ClearPath</strong><small>Finance</small></span>
          </Link>
          <button type="button" className={`${styles.iconButton} ${styles.mobileClose}`} aria-label="Close navigation" title="Close navigation" onClick={closeMobile}>
            <X size={20} aria-hidden="true" />
          </button>
        </div>

        <nav className={styles.navigation} aria-label="Primary navigation">
          <NavLink href="/dashboard" label="Today" icon={<Home size={18} aria-hidden="true" />} active={pathname === "/dashboard"} onNavigate={closeMobile} />

          <div className={`${styles.navGroup} ${planOpen ? styles.groupOpen : ""}`}>
            <div className={styles.groupRow}>
              <NavLink href="/monthly-plan?section=budgets" label="Plan" icon={<CalendarRange size={18} aria-hidden="true" />} active={pathname.startsWith("/monthly-plan") || pathname.startsWith("/cash-projections")} onNavigate={closeMobile} />
              <button type="button" className={styles.groupToggle} aria-label="Toggle Plan subtabs" title="Toggle Plan subtabs" aria-expanded={planOpen} onClick={() => setPlanOpen((open) => !open)}>
                <ChevronDown size={17} aria-hidden="true" />
              </button>
            </div>
            {planOpen ? (
              <div className={styles.subNavigation}>
                <NavLink href="/monthly-plan?section=budgets" label="Budgets" compact active={pathname === "/monthly-plan"} onNavigate={closeMobile} />
                <NavLink href="/monthly-plan?section=tools" label="Quick Planning" compact active={false} onNavigate={closeMobile} />
                <NavLink href="/monthly-plan?section=forecast" label="3-Month Forecast" compact active={false} onNavigate={closeMobile} />
                {visibleFeatures.has("income_planning") ? <NavLink href="/monthly-plan?section=baseline" label="Income Planning" compact active={false} onNavigate={closeMobile} /> : null}
                {visibleFeatures.has("cash_projection") ? <NavLink href="/cash-projections" label="Cash Balance Projections" compact active={pathname.startsWith("/cash-projections")} onNavigate={closeMobile} /> : null}
              </div>
            ) : null}
          </div>

          <div className={`${styles.navGroup} ${reviewOpen ? styles.groupOpen : ""}`}>
            <div className={styles.groupRow}>
              <NavLink href="/transactions" label="Review Transactions" icon={<ReceiptText size={18} aria-hidden="true" />} active={pathname.startsWith("/transactions") || pathname.startsWith("/subscriptions") || pathname.startsWith("/category-rules")} onNavigate={closeMobile} />
              <button type="button" className={styles.groupToggle} aria-label="Toggle Review Transactions subtabs" title="Toggle Review Transactions subtabs" aria-expanded={reviewOpen} onClick={() => setReviewOpen((open) => !open)}>
                <ChevronDown size={17} aria-hidden="true" />
              </button>
            </div>
            {reviewOpen ? (
              <div className={styles.subNavigation}>
                <NavLink href="/transactions" label="Transaction Review" compact active={pathname === "/transactions"} onNavigate={closeMobile} />
                {visibleFeatures.has("subscriptions") ? <NavLink href="/subscriptions" label="Subscriptions" compact active={pathname.startsWith("/subscriptions")} onNavigate={closeMobile} /> : null}
                <NavLink href="/category-rules" label="Categorization Rules" compact active={pathname.startsWith("/category-rules")} onNavigate={closeMobile} />
              </div>
            ) : null}
          </div>

          <NavLink href="/analytics" label="Analytics" icon={<BarChart3 size={18} aria-hidden="true" />} active={pathname.startsWith("/analytics")} onNavigate={closeMobile} />
          <NavLink href="/goals" label="Goals" icon={<Goal size={18} aria-hidden="true" />} active={pathname.startsWith("/goals")} onNavigate={closeMobile} />
          {featureEnabled(session, "ai_planner") ? <NavLink href="/planner" label="AI Planner" icon={<Sparkles size={18} aria-hidden="true" />} active={pathname.startsWith("/planner")} onNavigate={closeMobile} /> : null}
          {featureEnabled(session, "mortgage_loan_planning") ? <NavLink href="/loan-plans" label="Mortgage/Loan Planning" icon={<Landmark size={18} aria-hidden="true" />} active={pathname.startsWith("/loan-plans")} onNavigate={closeMobile} /> : null}
          {featureEnabled(session, "retirement_planning") ? <NavLink href="/retirement-plan" label="Retirement Planning" icon={<PiggyBank size={18} aria-hidden="true" />} active={pathname.startsWith("/retirement-plan")} onNavigate={closeMobile} /> : null}

          <div className={styles.utilityNav}>
            <NavLink href="/help" label="Help" icon={<CircleHelp size={18} aria-hidden="true" />} active={pathname.startsWith("/help")} onNavigate={closeMobile} />
            <NavLink href="/settings" label="Settings" icon={<Settings size={18} aria-hidden="true" />} active={pathname.startsWith("/settings")} onNavigate={closeMobile} />
          </div>
        </nav>

        <div className={styles.sidebarFooter}>
          <Link href="/feedback" className={styles.feedbackLink} onClick={closeMobile}><MessageSquareText size={17} aria-hidden="true" />Leave Feedback</Link>
          <details className={styles.accountMenu}>
            <summary>
              <span className={styles.avatar}>{session.subject.avatarInitial}</span>
              <span className={styles.accountIdentity}><strong>{session.subject.displayName}</strong><small>{session.subject.email}</small></span>
              <ChevronDown size={16} aria-hidden="true" />
            </summary>
            <div className={styles.accountActions}>
              <span>Current Plan<strong>{session.planDisplayName}</strong></span>
              {session.primaryAccountHolder ? <Link href="/select-plan">Upgrade Account</Link> : null}
              <Link href="/settings">Settings</Link>
              <Link href="/pricing">Plan Details</Link>
            </div>
          </details>
          <button type="button" className={styles.logoutButton} disabled={signingOut} onClick={() => void signOut()}>
            <LogOut size={17} aria-hidden="true" />{signingOut ? "Signing Out..." : "Sign Out"}
          </button>
        </div>
      </aside>

      <main className={styles.main}>{children}</main>
    </div>
  );
}
