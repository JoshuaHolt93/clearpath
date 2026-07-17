import type { components } from "@clearpath/api-client";
import { monthlyBudgetsViewSchema } from "@clearpath/validation";
import { NextResponse } from "next/server";

import { apiErrorMessage, clearPathApiClient, forwardedSessionHeaders } from "@/lib/server-api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type ApiMe = components["schemas"]["MeResponse"];
type ApiPlan = components["schemas"]["MonthlyPlanResponse"];
type ApiBudgetRow = components["schemas"]["BudgetRowResponse"];

const budgetSorts = new Set(["custom", "amount_desc", "amount_asc", "category_az", "category_za"]);

function mapSession(data: ApiMe) {
  return {
    ownerUserId: data.id,
    householdName: data.household_name ?? null,
    selectedPlan: data.selected_plan,
    billingStatus: data.billing_status,
    planDisplayName: data.plan_display_name,
    primaryAccountHolder: data.primary_account_holder,
    subject: {
      id: data.session_subject.id,
      subjectType: data.session_subject.subject_type,
      email: data.session_subject.email,
      displayName: data.session_subject.display_name,
      firstName: data.session_subject.first_name,
      avatarInitial: data.session_subject.avatar_initial,
      householdRole: data.session_subject.household_role ?? null,
    },
    featureAccess: (data.feature_access ?? []).map((row) => ({
      feature: row.feature,
      enabled: row.enabled,
      hidden: row.hidden,
      requiredPlan: row.required_plan,
    })),
  };
}

function mapBudgetRow(row: ApiBudgetRow) {
  return {
    kind: row.kind,
    categoryKind: row.category_kind,
    categoryId: row.category_id ?? null,
    label: row.label,
    category: row.category,
    groupKey: row.group_key,
    planned: row.planned,
    actual: row.actual,
    remaining: row.remaining,
    progressPercent: row.progress_percent,
    progressStatus: row.progress_status,
    anchorId: row.anchor_id,
    transactionIds: row.transaction_ids ?? [],
    transactionCount: row.transaction_count,
    suggestionMatchCount: row.suggestion_match_count,
    sortOrder: row.sort_order ?? null,
    canRemoveBudget: row.can_remove_budget,
    actualLabel: row.actual_label,
    plannedLabel: row.planned_label,
    adjustLabel: row.adjust_label,
    amortizationAction: row.amortization_action ? {
      action: row.amortization_action.action,
      fixedExpenseItemId: row.amortization_action.fixed_expense_item_id ?? null,
      label: row.amortization_action.label,
      hint: row.amortization_action.hint ?? null,
    } : null,
  };
}

function mapPlan(data: ApiPlan, me: ApiMe, onboardingComplete: boolean) {
  return monthlyBudgetsViewSchema.safeParse({
    session: mapSession(me),
    monthName: data.month_name,
    today: data.today,
    onboardingComplete,
    budgetView: data.budget_view,
    budgetGrouped: data.budget_grouped,
    budgetSort: data.budget_sort,
    budgetDragEnabled: data.budget_drag_enabled,
    budgetSelectedMonth: data.budget_selected_month,
    budgetCurrentMonth: data.budget_current_month,
    budgetMonthValue: data.budget_month_value,
    budgetMonthLabel: data.budget_month_label,
    budgetIsCurrentMonth: data.budget_is_current_month,
    budgetHistoryMode: data.budget_history_mode,
    totalBudgetPlanned: data.total_budget_planned,
    totalBudgetActual: data.total_budget_actual,
    totalBudgetRemaining: data.total_budget_remaining,
    expectedCashFlow: data.expected_cash_flow,
    budgetSections: (data.budget_sections ?? []).map((section) => ({
      label: section.label,
      kind: section.kind,
      description: section.description,
      empty: section.empty,
      rows: (section.rows ?? []).map(mapBudgetRow),
      planned: section.planned,
      actual: section.actual,
      transactionIds: section.transaction_ids ?? [],
      transactionCount: section.transaction_count,
    })),
    suggestedBudgetSections: (data.suggested_budget_sections ?? []).map((section) => ({
      label: section.label,
      kind: section.kind,
      rows: (section.rows ?? []).map(mapBudgetRow),
    })),
    unassignedBudgetRows: (data.unassigned_budget_rows ?? []).map(mapBudgetRow),
    categoryLabelOptions: data.category_label_options ?? [],
    budgetGroupOptions: (data.budget_group_options ?? []).map((group) => ({
      key: String(group.key ?? ""),
      label: String(group.label ?? ""),
      description: String(group.description ?? ""),
    })),
    budgetSortOptions: data.budget_sort_options ?? {},
  });
}

export async function GET(request: Request) {
  const url = new URL(request.url);
  const budgetView = url.searchParams.get("budget_view") === "grouped" ? "grouped" : "list";
  const requestedSort = url.searchParams.get("budget_sort") ?? "custom";
  const budgetSort = budgetSorts.has(requestedSort) ? requestedSort : "custom";
  const budgetMonth = url.searchParams.get("budget_month") ?? "";
  const headers = forwardedSessionHeaders(request);
  try {
    const [planResult, meResult] = await Promise.all([
      clearPathApiClient().GET("/v1/monthly-plan", {
        params: { query: { view: "month", section: "budgets", budget_view: budgetView, budget_sort: budgetSort, quick_sort: "amount_desc", budget_month: budgetMonth } },
        headers,
      }),
      clearPathApiClient().GET("/v1/me", { headers }),
    ]);
    if (!planResult.response.ok || !planResult.data) {
      return NextResponse.json({ message: apiErrorMessage(planResult.error, "We could not load your budgets.") }, { status: planResult.response.status });
    }
    if (!meResult.response.ok || !meResult.data) {
      return NextResponse.json({ message: apiErrorMessage(meResult.error, "We could not load your account session.") }, { status: meResult.response.status });
    }
    const mapped = mapPlan(planResult.data, meResult.data, url.searchParams.get("onboarding") === "complete");
    if (!mapped.success) return NextResponse.json({ message: "ClearPath returned invalid budget details." }, { status: 502 });
    return NextResponse.json(mapped.data, { headers: { "cache-control": "no-store" } });
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}
