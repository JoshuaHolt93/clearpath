import type { Metadata } from "next";

import { DashboardWorkspace } from "./dashboard-workspace";

export const metadata: Metadata = { title: "Today | ClearPath Finance" };

export default async function DashboardPage({ searchParams }: { searchParams: Promise<{ welcome?: string }> }) {
  const params = await searchParams;
  return <DashboardWorkspace initialWelcome={params.welcome === "1"} />;
}
