import type { Metadata } from "next";

import { AnalyticsWorkspace, type AnalyticsQuery } from "./analytics-workspace";

export const metadata: Metadata = { title: "Analytics | ClearPath Finance" };

function value(raw: string | string[] | undefined, fallback: string) {
  return Array.isArray(raw) ? raw[0] ?? fallback : raw ?? fallback;
}

export default async function AnalyticsPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const params = await searchParams;
  const query: AnalyticsQuery = {
    range: value(params.range, "month"),
    endMonth: value(params.end_month, ""),
    historyRange: value(params.history_range, "quarter"),
    historyEndMonth: value(params.history_end_month, ""),
  };
  return <AnalyticsWorkspace query={query} />;
}
