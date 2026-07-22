"use client";

import { plannerPageContextResponseSchema, type PlannerGuidanceItem, type SignedInSession } from "@clearpath/validation";
import {
  BarChart3,
  CalendarRange,
  ChevronDown,
  CircleHelp,
  CreditCard,
  Goal,
  Home,
  Landmark,
  LogOut,
  Menu,
  MessageSquareText,
  PiggyBank,
  ReceiptText,
  RefreshCw,
  Send,
  Settings,
  Sparkles,
  X,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { type FormEvent, type ReactNode, useCallback, useEffect, useMemo, useRef, useState } from "react";

import styles from "./authenticated-shell.module.css";

type AuthenticatedShellProps = {
  session: SignedInSession;
  activePlanSection?: "budgets" | "tools" | "forecast" | "baseline";
  children: ReactNode;
};

let navigationSession: SignedInSession | null = null;

export function clearNavigationSession() {
  navigationSession = null;
}

export function AuthenticatedPageFrame({ session, activePlanSection, children }: Omit<AuthenticatedShellProps, "session"> & { session?: SignedInSession | null }) {
  if (session) navigationSession = session;
  const activeSession = session ?? navigationSession;
  return activeSession
    ? <AuthenticatedShell session={activeSession} activePlanSection={activePlanSection}>{children}</AuthenticatedShell>
    : <>{children}</>;
}

function featureEnabled(session: SignedInSession, key: string): boolean {
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

type CoachMessage = {
  id: number;
  role: "user" | "assistant";
  question?: string;
  items?: PlannerGuidanceItem[];
  error?: string;
};

function pageContext() {
  const main = Array.from(document.querySelectorAll("main")).at(-1);
  const params = new URLSearchParams(window.location.search);
  return {
    path: window.location.pathname,
    title: document.title,
    section: params.get("section") ?? "",
    visibleText: (main?.innerText ?? "").slice(0, 3000),
  };
}

function AiCoach({ session }: { session: SignedInSession }) {
  const [open, setOpen] = useState(false);
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<CoachMessage[]>([]);
  const [busy, setBusy] = useState(false);
  const nextId = useRef(1);
  const promptHandled = useRef(false);
  const logRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const runCoach = useCallback(async (rawQuestion: string, hideUserPrompt = false) => {
    const nextQuestion = rawQuestion.trim();
    if (!nextQuestion || busy) return;
    setOpen(true);
    setBusy(true);
    if (!hideUserPrompt) setMessages((current) => [...current, { id: nextId.current++, role: "user", question: nextQuestion }]);
    try {
      const response = await fetch("/api/planner/page-context", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ ...pageContext(), question: nextQuestion }),
      });
      const body = await response.json().catch(() => null) as unknown;
      if (!response.ok) throw new Error((body as { message?: string } | null)?.message || "AI Coach could not review this page.");
      const parsed = plannerPageContextResponseSchema.safeParse(body);
      if (!parsed.success) throw new Error("AI Coach data did not match the expected contract.");
      setMessages((current) => [...current, { id: nextId.current++, role: "assistant", items: parsed.data.items }]);
    } catch (coachError) {
      setMessages((current) => [...current, { id: nextId.current++, role: "assistant", error: coachError instanceof Error ? coachError.message : "AI Coach could not review this page." }]);
    } finally {
      setBusy(false);
    }
  }, [busy]);

  useEffect(() => {
    const listener = (event: Event) => {
      const detail = (event as CustomEvent<{ prompt?: string; autoRun?: boolean }>).detail ?? {};
      setOpen(true);
      if (detail.autoRun && detail.prompt) {
        setQuestion("");
        void runCoach(detail.prompt, true);
      } else {
        setQuestion(detail.prompt ?? "");
        window.setTimeout(() => textareaRef.current?.focus(), 0);
      }
    };
    window.addEventListener("clearpath:open-ai-coach", listener);
    return () => window.removeEventListener("clearpath:open-ai-coach", listener);
  }, [runCoach]);

  useEffect(() => {
    if (promptHandled.current) return;
    const prompt = new URLSearchParams(window.location.search).get("prompt")?.trim();
    if (!prompt) return;
    promptHandled.current = true;
    setQuestion(prompt);
    void runCoach(prompt, true);
  }, [runCoach]);

  useEffect(() => {
    if (!open) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const closeOnEscape = (event: KeyboardEvent) => { if (event.key === "Escape") setOpen(false); };
    window.addEventListener("keydown", closeOnEscape);
    return () => { document.body.style.overflow = previousOverflow; window.removeEventListener("keydown", closeOnEscape); };
  }, [open]);

  useEffect(() => {
    const log = logRef.current;
    if (!log) return;
    if (typeof log.scrollTo === "function") log.scrollTo({ top: log.scrollHeight });
    else log.scrollTop = log.scrollHeight;
  }, [busy, messages]);

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!question.trim()) return textareaRef.current?.focus();
    const submitted = question;
    setQuestion("");
    void runCoach(submitted);
  };

  if (!featureEnabled(session, "ai_coach")) return null;
  const pageTitle = typeof document === "undefined" ? "ClearPath" : document.title.replace(" | ClearPath Finance", "");

  return <>
    {open ? <div className={styles.coachBackdrop} onMouseDown={(event) => { if (event.target === event.currentTarget) setOpen(false); }}>
      <aside className={styles.coachDrawer} role="dialog" aria-modal="true" aria-labelledby="coach-title">
        <header className={styles.coachHeader}><div className={styles.coachMark}>AI</div><div><h2 id="coach-title">Ask AI Coach</h2><p>Chat about this ClearPath page, planning workflow, or app insight.</p></div><button type="button" className={styles.iconButton} aria-label="Close AI Coach" title="Close AI Coach" onClick={() => setOpen(false)}><X size={18} aria-hidden="true" /></button></header>
        <div className={styles.coachContext}><div><small>Reviewing</small><strong>{pageTitle}</strong></div><span>Coaching Only</span></div>
        <div className={styles.chatLog} ref={logRef} aria-live="polite">
          {!messages.length ? <div className={`${styles.chatMessage} ${styles.assistantMessage}`}><div><strong>Hi, I am ClearPath&apos;s AI Coach.</strong><p>Ask me to explain something on this page, review a ClearPath workflow, or help interpret budgeting, transactions, subscriptions, goals, or cash-flow planning.</p></div></div> : null}
          {messages.map((message) => message.role === "user" ? <div className={`${styles.chatMessage} ${styles.userMessage}`} key={message.id}><div>{message.question}</div></div> : <div className={`${styles.chatMessage} ${styles.assistantMessage}`} key={message.id}><div>{message.error ? <><strong>AI Coach could not review this page.</strong><p>{message.error}</p></> : message.items?.length ? <div className={styles.coachItems}>{message.items.map((item, index) => <article key={`${item.title}-${index}`}><strong>{item.title}</strong><p>{item.body}</p></article>)}</div> : <><strong>No urgent notes</strong><p>Nothing on this page needs immediate attention based on the visible context.</p></>}</div></div>)}
          {busy ? <div className={`${styles.chatMessage} ${styles.assistantMessage}`}><div className={styles.coachLoading}><RefreshCw size={14} aria-hidden="true" />AI Coach is reviewing...</div></div> : null}
        </div>
        <form className={styles.coachForm} onSubmit={submit}><label htmlFor="coach-question">Ask a question about this page</label><div><textarea ref={textareaRef} id="coach-question" rows={3} value={question} disabled={busy} placeholder="Ask why a number changed or what to review next." onChange={(event) => setQuestion(event.target.value)} /><button type="submit" aria-label="Send to AI Coach" title="Send to AI Coach" disabled={busy || !question.trim()}><Send size={17} aria-hidden="true" /></button></div><div className={styles.coachSuggestions} aria-label="Suggested AI Coach prompts">{["What stands out on this page?", "What should I review next?", "Where might I be missing something?"].map((prompt) => <button type="button" disabled={busy} key={prompt} onClick={() => { setQuestion(""); void runCoach(prompt); }}>{prompt === "What stands out on this page?" ? "What stands out?" : prompt === "What should I review next?" ? "Review next" : "Blind spots"}</button>)}</div></form>
      </aside>
    </div> : null}
    <button type="button" className={styles.coachFloatingButton} onClick={() => { setOpen(true); window.setTimeout(() => textareaRef.current?.focus(), 0); }}><Sparkles size={17} aria-hidden="true" />Ask AI Coach</button>
  </>;
}

export function AuthenticatedShell({ session, activePlanSection, children }: AuthenticatedShellProps) {
  navigationSession = session;
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
    clearNavigationSession();
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
                <NavLink href="/monthly-plan?section=budgets" label="Budgets" compact active={pathname === "/monthly-plan" && activePlanSection === "budgets"} onNavigate={closeMobile} />
                <NavLink href="/monthly-plan?section=tools" label="Quick Planning" compact active={pathname === "/monthly-plan" && activePlanSection === "tools"} onNavigate={closeMobile} />
                <NavLink href="/monthly-plan?section=forecast" label="3-Month Forecast" compact active={pathname === "/monthly-plan" && activePlanSection === "forecast"} onNavigate={closeMobile} />
                {visibleFeatures.has("income_planning") ? <NavLink href="/monthly-plan?section=baseline" label="Income Planning" compact active={pathname === "/monthly-plan" && activePlanSection === "baseline"} onNavigate={closeMobile} /> : null}
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
            <NavLink href="/feedback" label="Feedback" icon={<MessageSquareText size={18} aria-hidden="true" />} active={pathname.startsWith("/feedback")} onNavigate={closeMobile} />
            {session.primaryAccountHolder ? <NavLink href="/billing" label="Billing" icon={<CreditCard size={18} aria-hidden="true" />} active={pathname.startsWith("/billing")} onNavigate={closeMobile} /> : null}
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
      <AiCoach session={session} />
    </div>
  );
}
