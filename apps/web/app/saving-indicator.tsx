"use client";

import { Loader2 } from "lucide-react";

import styles from "./saving-indicator.module.css";

/**
 * Shared "something is saving" affordance.
 *
 * Workspaces disable controls while a mutation is in flight but showed nothing
 * to explain why, so a ~230ms round trip read as the app freezing. Render this
 * next to the action being saved.
 */
export function SavingIndicator({ label = "Saving", className }: { label?: string; className?: string }) {
  return (
    <span className={className ? `${styles.indicator} ${className}` : styles.indicator} role="status">
      <Loader2 size={14} className={styles.spin} aria-hidden="true" />
      {label}
    </span>
  );
}
