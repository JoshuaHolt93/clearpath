import type { Metadata } from "next";

import { BillingWorkspace } from "../billing/billing-workspace";

export const metadata: Metadata = { title: "Select A Plan | ClearPath Finance" };

// Flask exposes plan selection as its own route (billing.select_plan) distinct
// from billing management, and the whole app links here: the post-MFA
// next_step, every upgrade CTA, and the 403 redirect in loan plans. The
// workspace already adapts its labels to whether a plan is set, so both routes
// render it.
export default function SelectPlanPage() {
  return <BillingWorkspace />;
}
