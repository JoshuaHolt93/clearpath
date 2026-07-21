import type { Metadata } from "next";

import { PolicyView } from "../(legal)/policy-view";
import { MONEY_TRANSMISSION_POLICY } from "@/lib/legal-content-policies";

export const metadata: Metadata = { title: "Money Transmission Scope | ClearPath Finance" };

export default function MoneyTransmissionScopePage() {
  return <PolicyView policy={MONEY_TRANSMISSION_POLICY} />;
}
