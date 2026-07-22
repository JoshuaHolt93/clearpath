"use client";

import { helpViewSchema, type HelpView } from "@clearpath/validation";
import { ArrowRight, BookOpen, CircleHelp } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { AuthenticatedPageFrame } from "../authenticated-shell";
import styles from "./help.module.css";

const HELP_TOPICS = [
  { slug: "today", title: "Today", summary: "Start here when you want the simplest read on the current month.", href: "/dashboard?welcome=1", steps: ["Check Month Progress to see whether spending is moving faster than the calendar.", "Use Current Month Plan vs Actual to compare budgeted amounts with real activity.", "Open Where The Money Went categories when you want to review the matching transactions."] },
  { slug: "budgets", title: "Budgets", summary: "Budgets are the monthly targets you review and adjust after transactions are categorized.", href: "/monthly-plan?section=budgets", steps: ["Review the Income budget that was preset from setup.", "Adjust category amounts after transactions start landing in each budget.", "Sort, reorder, delete, or organize categories when you are ready to clean up the list."] },
  { slug: "quick-planning", title: "Quick Planning", summary: "Use this worksheet to think through near-term cash position for the current month.", href: "/monthly-plan?section=tools", steps: ["Confirm the operating cash balance at the top.", "Review upcoming budgets and scheduled expenses in the worksheet.", "Use the 3-Month Forecast link when you need a longer view."] },
  { slug: "forecast", title: "3-Month Forecast", summary: "See how income and planned expenses affect cash over the next few months.", href: "/monthly-plan?section=forecast", steps: ["Review each month as income minus planned expenses.", "Open the planned items when a month needs more explanation.", "Add timing details when a one-time expense changes the forecast."] },
  { slug: "transactions", title: "Review Transactions", summary: "Clean up the activity that powers budgets, analytics, and monthly guidance.", href: "/transactions", steps: ["Filter or search when you want to focus on one merchant, account, category, or month.", "Pick a category for each transaction so the spending rolls into the right budget.", "Use Create Rule when the same merchant should be categorized automatically next time."] },
  { slug: "categorization-rules", title: "Categorization Rules", summary: "Rules teach ClearPath how to handle repeat merchants and descriptions.", href: "/category-rules", steps: ["Start with a specific description or merchant condition.", "Choose the category ClearPath should apply when a future transaction matches.", "Review saved rules if a merchant starts landing in the wrong category."] },
  { slug: "analytics", title: "Analytics", summary: "Use Analytics when you want to compare spending patterns after the day-to-day review is cleaner.", href: "/analytics", steps: ["Start with the Month view for the clearest current-month picture.", "Switch ranges only when you want a longer pattern.", "Return to transactions if a category looks off and needs cleanup."] },
  { slug: "goals", title: "Goals", summary: "Goals track progress toward a target; budgets manage planned monthly spending.", href: "/goals", steps: ["Use a goal for a target amount, payoff, or savings milestone.", "Use a budget for recurring monthly spending or income categories.", "Review both together when monthly cash decisions affect a bigger target."] },
  { slug: "subscriptions", title: "Consumer Subscriptions", summary: "Review recurring charges, next charge dates, and savings opportunities.", href: "/subscriptions", steps: ["Sort the list by priority, service, monthly amount, next charge, or confidence.", "Open Details when you need to review evidence behind a detected subscription.", "Mark subscriptions ignored or managed when they no longer need attention."] },
  { slug: "education", title: "Education Center", summary: "Learn the finance concepts tied to the tools available on your current plan.", href: "/education", steps: ["Start with the plan-focused learning card.", "Open a learning path that matches the workflow you are using.", "Use the external resources for broader education, not personalized advice."] },
  { slug: "settings", title: "Settings", summary: "Manage household access, bank connections, billing, security, and account controls.", href: "/settings", steps: ["Use Household Settings for shared access and billing context.", "Use Security & Privacy for password and multi-factor authentication controls.", "Review connected institutions when you need to remove or refresh bank access."] },
] as const;

function guideHref(href: string, slug: string) { return `${href}${href.includes("?") ? "&" : "?"}tutorial=${slug}`; }

export function HelpWorkspace({ selectedTopic }: { selectedTopic: string }) {
  const router = useRouter();
  const [data, setData] = useState<HelpView | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const response = await fetch("/api/help", { cache: "no-store" });
        if (response.status === 401) { router.replace("/login?next=/help"); return; }
        if (response.status === 403) { router.replace("/onboarding"); return; }
        const body = await response.json().catch(() => null) as unknown;
        if (!response.ok) throw new Error((body as { message?: string } | null)?.message || "We could not load Help.");
        const parsed = helpViewSchema.safeParse(body);
        if (!parsed.success) throw new Error("Help data did not match the expected contract.");
        if (!cancelled) setData(parsed.data);
      } catch (loadError) {
        if (!cancelled) setError(loadError instanceof Error ? loadError.message : "We could not load Help.");
      }
    })();
    return () => { cancelled = true; };
  }, [router]);
  const content = (
    <div className={styles.layout}>
      <header className={styles.header}><div><h1>Help</h1><p>Short guides for the pages and workflows you use in ClearPath.</p></div><Link href="/dashboard?welcome=1&tutorial=today" className={styles.secondaryAction}><CircleHelp size={16} aria-hidden="true" />Replay Today Tutorial</Link></header>
      <p className={styles.callout}>ClearPath works best when you move in a simple loop: check Today, clean up transactions, review budgets, then use analytics or goals when you want more context.</p>
      <div className={styles.overviewGrid}>
        <section className={styles.panel} aria-labelledby="start-here"><h2 id="start-here">Start Here</h2><div className={styles.startList}>
          <Link href="/dashboard?welcome=1&tutorial=today"><span><strong>Replay the Today tutorial</strong><small>See the short orientation card again on the Today page.</small></span><ArrowRight size={17} aria-hidden="true" /></Link>
          <Link href="/transactions"><span><strong>Clean up transactions</strong><small>Categorized transactions make budgets and analytics easier to trust.</small></span><ArrowRight size={17} aria-hidden="true" /></Link>
          <Link href="/category-rules"><span><strong>Create a categorization rule</strong><small>Teach repeat merchants to land in the right category automatically.</small></span><ArrowRight size={17} aria-hidden="true" /></Link>
        </div></section>
        <section className={styles.panel} aria-labelledby="main-tabs"><h2 id="main-tabs">How The Main Tabs Fit Together</h2><ol className={styles.flow}><li><span>1</span><div><strong>Today</strong><p>Use the top cards for the current month status.</p></div></li><li><span>2</span><div><strong>Review Transactions</strong><p>Fix categories so spending lands where it belongs.</p></div></li><li><span>3</span><div><strong>Budgets</strong><p>Adjust the plan once transaction data is cleaner.</p></div></li></ol></section>
      </div>
      <section className={styles.guides} aria-labelledby="page-guides"><header><h2 id="page-guides">Page Guides</h2><span>{HELP_TOPICS.length} Guides</span></header><div className={styles.guideGrid}>
        {HELP_TOPICS.map((topic) => <article key={topic.slug} id={topic.slug} className={selectedTopic === topic.slug ? styles.selected : ""}><div className={styles.guideHead}><div><h3>{topic.title}</h3><p>{topic.summary}</p></div><BookOpen size={18} aria-hidden="true" /></div><ol>{topic.steps.map((step) => <li key={step}>{step}</li>)}</ol><div className={styles.guideActions}><Link href={guideHref(topic.href, topic.slug)}>Guide</Link><Link href={topic.href}>Open</Link></div></article>)}
      </div></section>
    </div>
  );
  if (!data) return <AuthenticatedPageFrame><main className={styles.state}><p role={error ? "alert" : "status"}>{error || "Loading Help..."}</p></main></AuthenticatedPageFrame>;
  return <AuthenticatedPageFrame session={data.session}>{content}</AuthenticatedPageFrame>;
}
