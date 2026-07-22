import type { Metadata } from "next";

import { PricingWorkspace } from "./pricing-workspace";

export const metadata: Metadata = { title: "Plans And Pricing | ClearPath Finance" };

export default function PricingPage() {
  return <PricingWorkspace />;
}
