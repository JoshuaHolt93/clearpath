import type { Metadata } from "next";

import { GoalsWorkspace } from "./goals-workspace";

export const metadata: Metadata = { title: "Goals | ClearPath Finance" };

export default function GoalsPage() {
  return <GoalsWorkspace />;
}
