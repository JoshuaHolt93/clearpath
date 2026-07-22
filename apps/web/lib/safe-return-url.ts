/**
 * Port of Flask's `safe_local_return_url` (app/main.py:1335).
 *
 * A `return_to` value arrives from the query string, so it is attacker-
 * controllable. Only same-origin absolute paths are allowed: anything with a
 * scheme or host, or that does not start with "/", falls back to the default.
 * Protocol-relative "//evil.com" is rejected too -- it starts with "/" but
 * browsers treat it as cross-origin.
 */
export function safeLocalReturnUrl(target: string | null | undefined, fallback = ""): string {
  const value = (target ?? "").trim();
  if (!value || !value.startsWith("/") || value.startsWith("//")) return fallback;
  // Reject backslash variants that some browsers normalise to "//".
  if (value.startsWith("/\\") || value.includes("\\")) return fallback;
  try {
    // Resolve against a dummy origin; anything that escapes it is not local.
    const resolved = new URL(value, "https://clearpath.invalid");
    if (resolved.origin !== "https://clearpath.invalid") return fallback;
    return `${resolved.pathname}${resolved.search}${resolved.hash}`;
  } catch {
    return fallback;
  }
}

/**
 * Flask labels the control by destination (app/main.py:3146): budget-flow
 * returns say "Back to Budgets", everything else is generic.
 */
export function returnLabel(url: string): string {
  return url.startsWith("/monthly-plan") || url.startsWith("/budgets")
    ? "Back to Budgets"
    : "Back to previous page";
}
