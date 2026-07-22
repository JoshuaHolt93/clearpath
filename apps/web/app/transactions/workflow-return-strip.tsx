"use client";

import { ArrowLeft } from "lucide-react";
import Link from "next/link";

import { returnLabel, safeLocalReturnUrl } from "@/lib/safe-return-url";

import styles from "./transactions.module.css";

/**
 * Flask's `workflow-return-strip` (templates/transactions/index.html:321).
 *
 * When another workspace sends you here mid-task -- "Review Transactions" from
 * Budgets, say -- this offers the way back plus a reminder of why you came.
 * Without it the only route back is the browser's Back button, which loses the
 * filters the caller set up.
 */
export function WorkflowReturnStrip({ returnTo, categoryNames }: { returnTo: string; categoryNames?: string }) {
  const target = safeLocalReturnUrl(returnTo);
  if (!target) return null;

  // Flask picks the copy from what the caller was doing.
  const detail = categoryNames
    ? `Assign transactions to ${categoryNames}, then return to your budget planning.`
    : "Return to the workspace that sent you here.";

  return (
    <div className={styles.returnStrip}>
      <Link href={target} className={styles.secondaryButton}>
        <ArrowLeft size={16} aria-hidden="true" />
        {returnLabel(target)}
      </Link>
      <span>{detail}</span>
    </div>
  );
}
