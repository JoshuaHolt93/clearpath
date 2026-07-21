"use client";

/**
 * Kick off the stale-Plaid-item refresh without blocking a page render.
 *
 * `/v1/plaid-items/refresh-stale` is a synchronous endpoint that calls Plaid
 * for every stale item, so it can take many seconds or stall entirely.
 * Workspaces used to await it before their first data fetch, which left the
 * user staring at a loading screen with no timeout and no way out.
 *
 * Load your data first, then call this and reload only if `synced > 0`.
 */
export type LiveBankRefreshResult = {
  /** True when Plaid returned new data, so the caller should reload. */
  synced: boolean;
  /** User-facing warning, or null when there is nothing worth saying. */
  warning: string | null;
};

const REFRESH_TIMEOUT_MS = 20_000;

const WARNING = "Live bank refresh could not complete. Your saved data is still shown.";

export async function refreshLiveBankData(timeoutMs = REFRESH_TIMEOUT_MS): Promise<LiveBankRefreshResult> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch("/api/plaid-items/refresh-stale", { method: "POST", signal: controller.signal });
    // Viewers are not allowed to trigger a sync; that is expected, not a fault.
    if (response.status === 403) return { synced: false, warning: null };
    if (!response.ok) return { synced: false, warning: WARNING };
    const summary = await response.json().catch(() => null) as { synced?: number; errors?: unknown[] } | null;
    if (summary && Array.isArray(summary.errors) && summary.errors.length) {
      return { synced: Number(summary.synced ?? 0) > 0, warning: WARNING };
    }
    return { synced: Number(summary?.synced ?? 0) > 0, warning: null };
  } catch {
    // Aborted by the timeout, offline, or the request failed outright. The page
    // is already rendered with saved data, so this is a warning, not an error.
    return { synced: false, warning: WARNING };
  } finally {
    clearTimeout(timer);
  }
}
