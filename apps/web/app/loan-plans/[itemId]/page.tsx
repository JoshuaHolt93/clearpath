import type { Metadata } from "next";

import { LoanPlanWorkspace } from "./loan-plan-workspace";

export const metadata: Metadata = { title: "Loan Planning | ClearPath Finance" };

export default async function LoanPlanPage({ params }: { params: Promise<{ itemId: string }> }) {
  const { itemId } = await params;
  return <LoanPlanWorkspace itemId={itemId} />;
}
