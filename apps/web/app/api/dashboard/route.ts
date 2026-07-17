import type { components } from "@clearpath/api-client";
import { dashboardViewSchema } from "@clearpath/validation";
import { NextResponse } from "next/server";

import {
  apiErrorMessage,
  clearPathApiClient,
  forwardedSessionHeaders,
  requestCookieValue,
  setTodayTutorialCookie,
  TODAY_TUTORIAL_COOKIE,
} from "@/lib/server-api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type ApiDashboard = components["schemas"]["DashboardResponse"];
type ApiMe = components["schemas"]["MeResponse"];

function stringValue(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function numberValue(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

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

function mapDashboard(data: ApiDashboard, me: ApiMe, showTutorial: boolean) {
  return dashboardViewSchema.safeParse({
    session: mapSession(me),
    monthName: data.month_name,
    today: data.today,
    elapsedDays: data.elapsed_days,
    totalDays: data.total_days,
    daysLeft: data.days_left,
    pacePercent: data.pace_pct,
    spendPercent: data.spend_pct,
    showTutorial,
    metrics: {
      monthIncome: data.metrics.month_income,
      fixedExpenses: data.metrics.fixed_expenses,
      variableSpend: data.metrics.variable_spend,
      safeToSpend: data.metrics.safe_to_spend,
      safeToSpendTarget: data.metrics.safe_to_spend_target,
      netCashFlow: data.metrics.net_cash_flow,
      onTrackStatus: data.metrics.on_track_status,
      expectedVariableSpend: data.metrics.expected_variable_spend,
    },
    netWorth: {
      assets: data.net_worth.assets,
      liabilities: data.net_worth.liabilities,
      netWorth: data.net_worth.net_worth,
    },
    categoryTotals: (data.category_totals ?? []).map((row) => ({
      category: row.category,
      categoryId: row.category_id ?? null,
      amount: row.amount,
    })),
    goals: (data.goals ?? []).map((row) => ({
      id: row.goal.id,
      name: row.goal.name,
      goalType: row.goal.goal_type,
      progress: row.progress,
      timeline: row.timeline,
      currentAmount: row.current_amount,
      targetAmount: row.target_amount,
      requiredMonthly: row.required_monthly,
      requiredExtra: row.required_extra,
      targetDate: row.goal.target_date ?? null,
    })),
    recentTransactions: (data.recent_transactions ?? []).map((row) => ({
      id: row.id,
      postedDate: row.posted_date,
      description: row.description,
      amount: row.amount,
      transactionType: row.transaction_type,
      categoryName: row.category?.name ?? null,
    })),
    planRows: (data.plan_rows ?? []).map((row) => ({
      label: row.label,
      planned: row.planned,
      actual: row.actual,
      type: row.type,
      details: (row.details ?? []).map((rawDetail) => {
        const detail = rawDetail as Record<string, unknown>;
        return {
          label: stringValue(detail.label),
          planned: numberValue(detail.planned),
          actual: numberValue(detail.actual),
          source: stringValue(detail.source) || null,
        };
      }),
    })),
    budgetRemaining: data.budget_remaining,
    expectedCashFlow: data.expected_cash_flow,
    insights: (data.insights ?? []).map((row) => ({
      title: row.title,
      body: row.body,
      level: row.level,
      type: row.type,
      disclaimer: row.disclaimer,
    })),
    dashboardFocus: data.dashboard_focus ? {
      items: (data.dashboard_focus.items ?? []).map((row) => ({
        title: row.title,
        body: row.body,
        level: row.level,
        type: row.type,
        disclaimer: row.disclaimer ?? null,
        action: row.action ? { label: row.action.label, target: row.action.target } : null,
      })),
      generatedAt: data.dashboard_focus.generated_at ?? null,
      message: data.dashboard_focus.message,
    } : null,
  });
}

export async function GET(request: Request) {
  const headers = forwardedSessionHeaders(request);
  try {
    const [dashboardResult, meResult] = await Promise.all([
      clearPathApiClient().GET("/v1/dashboard", { headers }),
      clearPathApiClient().GET("/v1/me", { headers }),
    ]);
    if (!dashboardResult.response.ok || !dashboardResult.data) {
      return NextResponse.json(
        { message: apiErrorMessage(dashboardResult.error, "We could not load your dashboard.") },
        { status: dashboardResult.response.status },
      );
    }
    if (!meResult.response.ok || !meResult.data) {
      return NextResponse.json(
        { message: apiErrorMessage(meResult.error, "We could not load your account session.") },
        { status: meResult.response.status },
      );
    }
    const tutorialCookie = requestCookieValue(request, TODAY_TUTORIAL_COOKIE) === "1";
    const showTutorial = tutorialCookie || new URL(request.url).searchParams.get("welcome") === "1";
    const mapped = mapDashboard(dashboardResult.data, meResult.data, showTutorial);
    if (!mapped.success) {
      return NextResponse.json({ message: "ClearPath returned invalid dashboard details." }, { status: 502 });
    }
    const response = NextResponse.json(mapped.data, { headers: { "cache-control": "no-store" } });
    if (tutorialCookie) {
      setTodayTutorialCookie(response, false);
    }
    return response;
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}
