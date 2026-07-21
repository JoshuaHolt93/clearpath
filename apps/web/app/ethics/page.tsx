import type { Metadata } from "next";

import { PolicyView } from "../(legal)/policy-view";
import { ETHICS_POLICY } from "@/lib/legal-content-policies";

export const metadata: Metadata = { title: "Ethics Policy | ClearPath Finance" };

export default function EthicsPage() {
  return <PolicyView policy={ETHICS_POLICY} />;
}
