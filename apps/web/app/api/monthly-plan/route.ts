import type { components } from "@clearpath/api-client";
import { monthlyBudgetsViewSchema, monthlyForecastViewSchema, monthlyIncomePlanningViewSchema, monthlyQuickPlanningViewSchema } from "@clearpath/validation";
import { NextResponse } from "next/server";

import { apiErrorMessage, clearPathApiClient, forwardedSessionHeaders } from "@/lib/server-api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type ApiMe = components["schemas"]["MeResponse"];
type ApiPlan = components["schemas"]["MonthlyPlanResponse"];
type ApiBudgetRow = components["schemas"]["BudgetRowResponse"];

const budgetSorts = new Set(["custom", "amount_desc", "amount_asc", "category_az", "category_za"]);
const quickSorts = new Set(["amount_desc", "amount_asc", "name_asc", "name_desc", "timing_asc", "timing_desc", "category_az", "category_za"]);

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

function mapBudgetPlan(data: ApiPlan, me: ApiMe, onboardingComplete: boolean) {
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

function mapFixedItem(row: ApiPlan["fixed_items"][number]) {
  return {
    id: row.id, name: row.name, amount: row.amount, dueDay: row.due_day ?? null,
    startDate: row.start_date, frequency: row.frequency, daysOfWeek: row.days_of_week ?? null,
    secondDate: row.second_date ?? null, secondDayOfMonth: row.second_day_of_month ?? null,
    monthlyWeekNumbers: row.monthly_week_numbers ?? null, monthlyWeekday: row.monthly_weekday ?? null,
    categoryLabel: row.category_label ?? null, isLoan: row.is_loan, notes: row.notes ?? null,
    monthlyAmount: row.monthly_amount ?? null,
  };
}

function mapVariableItem(row: ApiPlan["variable_items"][number]) {
  return {
    id: row.id, name: row.name, amount: row.amount, frequency: row.frequency,
    useSpecificDate: row.use_specific_date, specificDate: row.specific_date ?? null,
    daysOfWeek: row.days_of_week ?? null, categoryLabel: row.category_label ?? null,
    notes: row.notes ?? null, monthlyAmount: row.monthly_amount ?? null,
  };
}

function mapForecastItem(row: ApiPlan["forecast_items"][number]) {
  return {
    id: row.id, itemDate: row.item_date, description: row.description, amount: row.amount,
    itemType: row.item_type, categoryLabel: row.category_label ?? null, notes: row.notes ?? null,
  };
}

function mapRecurringTemplate(row: ApiPlan["recurring_templates"][number]) {
  return {
    id: row.id, name: row.name, amount: row.amount, itemType: row.item_type, frequency: row.frequency,
    startDate: row.start_date, secondDate: row.second_date ?? null, daysOfWeek: row.days_of_week ?? null,
    secondDayOfMonth: row.second_day_of_month ?? null, monthlyWeekNumbers: row.monthly_week_numbers ?? null,
    monthlyWeekday: row.monthly_weekday ?? null, categoryLabel: row.category_label ?? null,
    notes: row.notes ?? null, incomeReplacement: row.income_replacement,
    incomeBasis: row.income_basis ?? null, incomeType: row.income_type ?? null,
    paycheckCadence: row.paycheck_cadence ?? null, incomeNextPayDate: row.income_next_pay_date ?? null,
    hourlyHoursPerWeek: row.hourly_hours_per_week, additionalIncomeAmount: row.additional_income_amount,
    additionalIncomeFrequency: row.additional_income_frequency, taxState: row.tax_state ?? null,
    taxFilingStatus: row.tax_filing_status ?? null, includePayrollTaxes: row.include_payroll_taxes,
    monthlyAmount: row.monthly_amount ?? null,
  };
}

function mapQuickPlan(data: ApiPlan, me: ApiMe) {
  const profile = data.profile;
  const projection = data.quick_cash_projection;
  return monthlyQuickPlanningViewSchema.safeParse({
    session: mapSession(me),
    monthName: data.month_name,
    today: data.today,
    quickSort: data.quick_sort,
    quickSortOptions: data.quick_sort_options ?? {},
    totalBudgetPlanned: data.total_budget_planned,
    fixedTotal: data.fixed_total,
    variablePlanTotal: data.variable_plan_total,
    quickCashRemainingIncome: data.quick_cash_remaining_income,
    quickCashRemainingExpenses: data.quick_cash_remaining_expenses,
    quickCashWeekChange: data.quick_cash_week_change,
    quickCashWeekEndBalance: data.quick_cash_week_end_balance,
    quickCashProjection: projection ? {
      endDate: projection.end_date,
      endBalance: projection.end_balance,
      balanceAnchor: {
        balance: projection.balance_anchor.balance,
        checkingBalance: projection.balance_anchor.checking_balance,
        accountCount: projection.balance_anchor.account_count,
        checkingAccountCount: projection.balance_anchor.checking_account_count,
        usesCashAccounts: projection.balance_anchor.uses_cash_accounts,
        includedAccounts: (projection.balance_anchor.included_accounts ?? []).map((account) => ({
          id: account.id, name: account.name, institution: account.institution ?? null,
          accountType: account.account_type, balance: account.balance, mask: account.mask ?? null,
          cashProjectionRole: account.cash_projection_role,
        })),
      },
      lowestBalance: { date: projection.lowest_balance.date, balance: projection.lowest_balance.balance },
    } : null,
    cashProjectionAccountRows: (data.cash_projection_account_rows ?? []).map((row) => ({
      accountId: row.account_id, name: row.name, institution: row.institution ?? null,
      accountType: row.account_type, balance: row.balance, mask: row.mask ?? null,
      role: row.role, included: row.included, statusLabel: row.status_label,
      statusClass: row.status_class, statusDetail: row.status_detail,
    })),
    quickWorksheetRows: (data.quick_worksheet_rows ?? []).map((row) => ({
      name: row.name, subtitle: row.subtitle, timing: row.timing, category: row.category,
      amount: row.amount, actionLabel: row.action_label, readonly: row.readonly,
      itemType: row.item_type, itemId: row.item_id ?? null,
    })),
    fixedItems: (data.fixed_items ?? []).map(mapFixedItem),
    variableItems: (data.variable_items ?? []).map(mapVariableItem),
    forecastItems: (data.forecast_items ?? []).map(mapForecastItem),
    recurringTemplates: (data.recurring_templates ?? []).map(mapRecurringTemplate),
    categoryLabelOptions: data.category_label_options ?? [],
    profile: {
      householdName: profile.household_name ?? null,
      incomeAmount: profile.income_amount ?? null,
      incomeAmountDisplay: profile.income_amount_display ?? null,
      monthlyIncome: profile.monthly_income ?? null,
      incomeBasis: profile.income_basis ?? null,
      incomeType: profile.income_type ?? null,
      incomeFrequency: profile.income_frequency ?? null,
      paycheckCadence: profile.paycheck_cadence ?? null,
      nextPayDate: profile.next_pay_date ?? null,
      paycheckSecondDate: profile.paycheck_second_date ?? null,
      paycheckDaysOfWeek: profile.paycheck_days_of_week ?? null,
      paycheckSecondDayOfMonth: profile.paycheck_second_day_of_month ?? null,
      paycheckMonthlyWeekNumbers: profile.paycheck_monthly_week_numbers ?? null,
      paycheckMonthlyWeekday: profile.paycheck_monthly_weekday ?? null,
      hourlyHoursPerWeek: profile.hourly_hours_per_week ?? null,
      additionalIncomeAmount: profile.additional_income_amount ?? null,
      additionalIncomeFrequency: profile.additional_income_frequency ?? null,
      taxState: profile.tax_state ?? null,
      taxFilingStatus: profile.tax_filing_status ?? null,
      includePayrollTaxes: profile.include_payroll_taxes ?? null,
      notes: profile.notes ?? null,
    },
    planIncome: data.plan.income,
    incomeTypeOptions: data.income_type_options ?? {},
    incomeBasisOptions: data.income_basis_options ?? {},
    paycheckCadenceOptions: data.paycheck_cadence_options ?? {},
    taxFilingStatusOptions: data.tax_filing_status_options ?? {},
    stateOptions: data.state_options ?? {},
    recurringFrequencyOptions: data.recurring_frequency_options ?? {},
    weekdayOptions: data.weekday_options ?? {},
    monthlyWeekOptions: data.monthly_week_options ?? {},
  });
}

function mapForecastPlan(data: ApiPlan, me: ApiMe) {
  return monthlyForecastViewSchema.safeParse({
    session: mapSession(me),
    today: data.today,
    forecastMonths: (data.forecast_months ?? []).map((month) => ({
      monthStart: month.month_start,
      monthName: month.month_name,
      baselineIncome: month.baseline_income,
      fixedExpenses: month.fixed_expenses,
      plannedSavings: month.planned_savings,
      plannedDebt: month.planned_debt,
      plannedTaxes: month.planned_taxes,
      plannedRetirement: month.planned_retirement,
      plannedVariable: month.planned_variable,
      plannedIncome: month.planned_income,
      plannedExpenses: month.planned_expenses,
      oneTimeIncome: month.one_time_income,
      oneTimeExpenses: month.one_time_expenses,
      forecastIncomeTotal: month.forecast_income_total,
      forecastExpenseTotal: month.forecast_expense_total,
      plannedBuffer: month.planned_buffer,
      startingCash: month.starting_cash,
      endingCash: month.ending_cash,
      forecastItems: (month.forecast_items ?? []).map((item) => ({
        date: item.date,
        description: item.description,
        amount: item.amount,
        itemType: item.item_type,
        source: item.source,
        sourceId: item.source_id ?? null,
        categoryLabel: item.category_label ?? null,
        notes: item.notes ?? null,
      })),
    })),
    forecastItems: (data.forecast_items ?? []).map(mapForecastItem),
    categoryLabelOptions: data.category_label_options ?? [],
  });
}

function mapIncomePlan(data: ApiPlan, me: ApiMe) {
  const profile = data.profile;
  const tax = data.tax_estimate;
  return monthlyIncomePlanningViewSchema.safeParse({
    session: mapSession(me),
    today: data.today,
    profile: {
      householdName: profile.household_name ?? null,
      incomeAmount: profile.income_amount ?? null,
      incomeAmountDisplay: profile.income_amount_display ?? null,
      monthlyIncome: profile.monthly_income ?? null,
      incomeBasis: profile.income_basis ?? null,
      incomeType: profile.income_type ?? null,
      incomeFrequency: profile.income_frequency ?? null,
      paycheckCadence: profile.paycheck_cadence ?? null,
      nextPayDate: profile.next_pay_date ?? null,
      paycheckSecondDate: profile.paycheck_second_date ?? null,
      paycheckDaysOfWeek: profile.paycheck_days_of_week ?? null,
      paycheckSecondDayOfMonth: profile.paycheck_second_day_of_month ?? null,
      paycheckMonthlyWeekNumbers: profile.paycheck_monthly_week_numbers ?? null,
      paycheckMonthlyWeekday: profile.paycheck_monthly_weekday ?? null,
      hourlyHoursPerWeek: profile.hourly_hours_per_week ?? null,
      additionalIncomeAmount: profile.additional_income_amount ?? null,
      additionalIncomeFrequency: profile.additional_income_frequency ?? null,
      taxState: profile.tax_state ?? null,
      taxFilingStatus: profile.tax_filing_status ?? null,
      taxAdditionalLabel: profile.tax_additional_label ?? null,
      taxAdditionalType: profile.tax_additional_type ?? null,
      taxAdditionalRate: profile.tax_additional_rate ?? null,
      taxAdditionalMonthlyAmount: profile.tax_additional_monthly_amount ?? null,
      includePayrollTaxes: profile.include_payroll_taxes ?? null,
      notes: profile.notes ?? null,
    },
    planIncome: data.plan.income,
    futureIncomeTemplates: (data.future_income_templates ?? []).map(mapRecurringTemplate),
    taxEstimate: {
      annualGrossIncome: tax.annual_gross_income,
      taxableIncome: tax.taxable_income,
      federalIncomeTax: tax.federal_income_tax,
      stateIncomeTax: tax.state_income_tax,
      socialSecurityTax: tax.social_security_tax,
      medicareTax: tax.medicare_tax,
      additionalMedicareTax: tax.additional_medicare_tax,
      additionalTaxLabel: tax.additional_tax_label,
      additionalTaxType: tax.additional_tax_type,
      additionalTaxRate: tax.additional_tax_rate,
      additionalTaxAnnual: tax.additional_tax_annual,
      additionalTaxMonthly: tax.additional_tax_monthly,
      annualTotal: tax.annual_total,
      monthlyTotal: tax.monthly_total,
      filingStatus: tax.filing_status,
      state: tax.state ?? null,
      stateRate: tax.state_rate,
      stateMethod: tax.state_method,
      stateTaxableIncome: tax.state_taxable_income,
      stateStandardDeduction: tax.state_standard_deduction,
      statePersonalExemption: tax.state_personal_exemption,
      stateCredit: tax.state_credit,
      stateBrackets: tax.state_brackets ?? [],
      stateNote: tax.state_note,
      stateSourceUrl: tax.state_source_url ?? null,
      federalBrackets: tax.federal_brackets ?? [],
      standardDeduction: tax.standard_deduction,
    },
    taxesEnabled: data.taxes_enabled,
    incomeTypeOptions: data.income_type_options ?? {},
    incomeBasisOptions: data.income_basis_options ?? {},
    paycheckCadenceOptions: data.paycheck_cadence_options ?? {},
    taxFilingStatusOptions: data.tax_filing_status_options ?? {},
    stateOptions: data.state_options ?? {},
    recurringFrequencyOptions: data.recurring_frequency_options ?? {},
    weekdayOptions: data.weekday_options ?? {},
    monthlyWeekOptions: data.monthly_week_options ?? {},
  });
}

export async function GET(request: Request) {
  const url = new URL(request.url);
  const requestedSection = url.searchParams.get("section");
  const section = requestedSection === "tools" || requestedSection === "forecast" || requestedSection === "baseline" ? requestedSection : "budgets";
  const resourceLabel = section === "budgets" ? "budgets" : section === "forecast" ? "forecast" : section === "baseline" ? "income plan" : "planning details";
  const budgetView = url.searchParams.get("budget_view") === "grouped" ? "grouped" : "list";
  const requestedSort = url.searchParams.get("budget_sort") ?? "custom";
  const budgetSort = budgetSorts.has(requestedSort) ? requestedSort : "custom";
  const budgetMonth = url.searchParams.get("budget_month") ?? "";
  const requestedQuickSort = url.searchParams.get("quick_sort") ?? "amount_desc";
  const quickSort = quickSorts.has(requestedQuickSort) ? requestedQuickSort : "amount_desc";
  const headers = forwardedSessionHeaders(request);
  try {
    const [planResult, meResult] = await Promise.all([
      clearPathApiClient().GET("/v1/monthly-plan", {
        params: { query: { view: "month", section, budget_view: budgetView, budget_sort: budgetSort, quick_sort: quickSort, budget_month: budgetMonth } },
        headers,
      }),
      clearPathApiClient().GET("/v1/me", { headers }),
    ]);
    if (!planResult.response.ok || !planResult.data) {
      return NextResponse.json({ message: apiErrorMessage(planResult.error, `We could not load your ${resourceLabel}.`) }, { status: planResult.response.status });
    }
    if (!meResult.response.ok || !meResult.data) {
      return NextResponse.json({ message: apiErrorMessage(meResult.error, "We could not load your account session.") }, { status: meResult.response.status });
    }
    const mapped = section === "tools"
      ? mapQuickPlan(planResult.data, meResult.data)
      : section === "forecast"
        ? mapForecastPlan(planResult.data, meResult.data)
        : section === "baseline"
          ? mapIncomePlan(planResult.data, meResult.data)
          : mapBudgetPlan(planResult.data, meResult.data, url.searchParams.get("onboarding") === "complete");
    const detailLabel = section === "budgets" ? "budget" : section === "forecast" ? "forecast" : section === "baseline" ? "income planning" : "planning";
    if (!mapped.success) return NextResponse.json({ message: `ClearPath returned invalid ${detailLabel} details.` }, { status: 502 });
    return NextResponse.json(mapped.data, { headers: { "cache-control": "no-store" } });
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}
