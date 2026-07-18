import type { Metadata } from "next";

import { CashProjectionWorkspace, type CashProjectionQuery } from "./cash-projection-workspace";

export const metadata: Metadata = { title: "Cash Balance Projections | ClearPath Finance" };

const horizons = new Set(["week", "1m", "3m", "6m", "custom"]);
const views = new Set(["calendar", "list", "graph"]);

export default async function CashProjectionsPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const params = await searchParams;
  const rawHorizon = typeof params.horizon === "string" ? params.horizon : undefined;
  const rawView = typeof params.view === "string" ? params.view : "calendar";
  const query: CashProjectionQuery = {
    month: typeof params.month === "string" ? params.month : "",
    horizon: rawHorizon && horizons.has(rawHorizon) ? rawHorizon as CashProjectionQuery["horizon"] : undefined,
    view: views.has(rawView) ? rawView as CashProjectionQuery["view"] : "calendar",
    startDate: typeof params.start_date === "string" ? params.start_date : "",
    endDate: typeof params.end_date === "string" ? params.end_date : "",
  };
  return <CashProjectionWorkspace query={query} />;
}
