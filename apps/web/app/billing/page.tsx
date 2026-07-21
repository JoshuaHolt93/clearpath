import type { Metadata } from "next";

import { BillingWorkspace } from "./billing-workspace";

export const metadata: Metadata = { title: "Billing | ClearPath Finance" };

export default function BillingPage() {
  return <BillingWorkspace />;
}
