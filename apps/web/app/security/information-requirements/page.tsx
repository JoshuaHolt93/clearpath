import type { Metadata } from "next";

import { PolicyView } from "../../(legal)/policy-view";
import { INFORMATION_REQUIREMENTS_POLICY } from "@/lib/legal-content-policies";

export const metadata: Metadata = { title: "Information Requirements | ClearPath Finance" };

export default function InformationRequirementsPage() {
  return <PolicyView policy={INFORMATION_REQUIREMENTS_POLICY} />;
}
