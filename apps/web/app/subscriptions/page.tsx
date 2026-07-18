import type { Metadata } from "next";

import { SubscriptionsWorkspace, type SubscriptionQuery } from "./subscriptions-workspace";

export const metadata: Metadata = { title: "Subscriptions | ClearPath Finance" };

function value(raw: string | string[] | undefined, fallback = "") {
  return Array.isArray(raw) ? raw[0] ?? fallback : raw ?? fallback;
}

export default async function SubscriptionsPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const params = await searchParams;
  const sortAlias: Record<string, string> = { savings: "priority", amount: "amount_desc", next: "next_asc", confidence: "confidence_desc" };
  const rawSort = value(params.sort, "priority");
  const sort = sortAlias[rawSort] ?? rawSort;
  const allowedSorts = new Set(["priority", "amount_desc", "amount_asc", "next_asc", "next_desc", "confidence_desc", "confidence_asc", "name_az", "name_za"]);
  const query: SubscriptionQuery = {
    q: value(params.q).trim().toLowerCase(),
    status: value(params.status, "all"),
    sort: allowedSorts.has(sort) ? sort : "priority",
  };
  return <SubscriptionsWorkspace query={query} />;
}
