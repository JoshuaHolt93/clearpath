"use client";

import { usePathname, useSearchParams } from "next/navigation";

/**
 * The caller's current location, for handing to a workspace you are sending
 * the user into mid-task.
 *
 * Transactions renders Flask's workflow-return-strip from `return_to`, so a
 * user who detours to clean something up can get back to what they were doing
 * with their filters intact instead of hunting through the nav.
 */
export function useReturnTo(): string {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const query = searchParams.toString();
  return `${pathname}${query ? `?${query}` : ""}`;
}

/** Append `return_to` to a link, preserving any query string it already has. */
export function withReturnTo(href: string, returnTo: string): string {
  if (!returnTo) return href;
  const separator = href.includes("?") ? "&" : "?";
  return `${href}${separator}return_to=${encodeURIComponent(returnTo)}`;
}
