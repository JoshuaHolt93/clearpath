import type { Metadata } from "next";

import { RetirementWorkspace } from "./retirement-workspace";

export const metadata: Metadata = { title: "Retirement Planning | ClearPath Finance" };

export default function RetirementPage() {
  return <RetirementWorkspace />;
}
