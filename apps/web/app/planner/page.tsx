import type { Metadata } from "next";

import { PlannerWorkspace } from "./planner-workspace";

export const metadata: Metadata = { title: "AI Planner | ClearPath Finance" };

export default function PlannerPage() {
  return <PlannerWorkspace />;
}
