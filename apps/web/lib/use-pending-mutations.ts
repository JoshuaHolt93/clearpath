"use client";

import { useCallback, useMemo, useState } from "react";

/**
 * Tracks in-flight mutations by key so a save on one control does not disable
 * every other control on the page.
 *
 * Workspaces previously shared a single `busy` boolean: categorizing one
 * transaction disabled every dropdown in the list, with no indication that
 * anything was happening. The round trip is ~230ms, so the app read as frozen
 * rather than slow.
 *
 * Keys default to the request URL, which already identifies the row
 * (`/api/transactions/123/category`), so per-row isolation comes for free.
 */
export function usePendingMutations() {
  const [pending, setPending] = useState<ReadonlySet<string>>(() => new Set<string>());

  const start = useCallback((key: string) => {
    setPending((current) => {
      const next = new Set(current);
      next.add(key);
      return next;
    });
  }, []);

  const stop = useCallback((key: string) => {
    setPending((current) => {
      if (!current.has(key)) return current;
      const next = new Set(current);
      next.delete(key);
      return next;
    });
  }, []);

  /** True when this exact key is saving. */
  const isPending = useCallback((key: string) => pending.has(key), [pending]);

  /**
   * True when any in-flight key contains `fragment`. Lets a row disable only
   * its own controls by matching on its id segment, without every child
   * component having to know about mutation keys.
   */
  const isPendingMatching = useCallback(
    (fragment: string) => {
      for (const key of pending) if (key.includes(fragment)) return true;
      return false;
    },
    [pending],
  );

  const anyPending = useMemo(() => pending.size > 0, [pending]);

  return { isPending, isPendingMatching, anyPending, start, stop };
}
