import type { Metadata } from "next";

import { ComplianceWorkspace } from "./compliance-workspace";

export const metadata: Metadata = { title: "Compliance | ClearPath Finance" };

export default function CompliancePage() {
  return <ComplianceWorkspace />;
}
