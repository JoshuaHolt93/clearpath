import type { Metadata } from "next";

import { PolicyView } from "../../(legal)/policy-view";
import { PCI_SAQ_A_POLICY } from "@/lib/legal-content-policies";

export const metadata: Metadata = { title: "PCI SAQ-A Policy | ClearPath Finance" };

export default function PciSaqAPage() {
  return <PolicyView policy={PCI_SAQ_A_POLICY} />;
}
