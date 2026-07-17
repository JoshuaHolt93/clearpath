import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { MonthlyBudgetsWorkspace, type MonthlyBudgetQuery } from "./monthly-budgets-workspace";
import { MonthlyQuickPlanningWorkspace, type MonthlyQuickPlanningQuery } from "./monthly-quick-planning-workspace";

export const metadata: Metadata = { title: "Monthly Plan | ClearPath Finance" };

const validSorts = new Set(["custom", "amount_desc", "amount_asc", "category_az", "category_za"]);
const validQuickSorts = new Set(["amount_desc", "amount_asc", "name_asc", "name_desc", "timing_asc", "timing_desc", "category_az", "category_za"]);

export default async function MonthlyPlanPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const params = await searchParams;
  const section = typeof params.section === "string" ? params.section : "budgets";
  if (section === "tools") {
    const requestedQuickSort = typeof params.quick_sort === "string" ? params.quick_sort : "amount_desc";
    const query: MonthlyQuickPlanningQuery = { quickSort: validQuickSorts.has(requestedQuickSort) ? requestedQuickSort : "amount_desc" };
    return <MonthlyQuickPlanningWorkspace query={query} />;
  }
  if (section !== "budgets") redirect("/monthly-plan?section=budgets");
  const requestedSort = typeof params.budget_sort === "string" ? params.budget_sort : "custom";
  const query: MonthlyBudgetQuery = {
    budgetView: params.budget_view === "grouped" ? "grouped" : "list",
    budgetSort: validSorts.has(requestedSort) ? requestedSort : "custom",
    budgetMonth: typeof params.budget_month === "string" ? params.budget_month : "",
    onboardingComplete: params.onboarding === "complete",
  };
  return <MonthlyBudgetsWorkspace query={query} />;
}
