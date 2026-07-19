import type { Metadata } from "next";

import { LoanDirectoryWorkspace } from "./loan-directory-workspace";

export const metadata: Metadata = { title: "Mortgage/Loan Planning | ClearPath Finance" };

export default function LoanPlansPage() {
  return <LoanDirectoryWorkspace />;
}
