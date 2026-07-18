import type { components } from "@clearpath/api-client";
import { cashProjectionViewSchema } from "@clearpath/validation";

type ApiCashProjection = components["schemas"]["CashProjectionResponse"];
type ApiCashEvent = components["schemas"]["CashProjectionEventResponse"];
type ApiCashDay = components["schemas"]["CashProjectionDayResponse"];
type ApiCashGraph = components["schemas"]["CashProjectionGraphResponse"];
type ApiCashPeriod = components["schemas"]["CashProjectionPeriodResponse"];
type ApiCalendarFeed = components["schemas"]["CashProjectionCalendarFeedResponse"];

function mapEvent(row: ApiCashEvent) {
  return {
    date: row.date,
    description: row.description,
    amount: row.amount,
    itemType: row.item_type,
    source: row.source,
    categoryLabel: row.category_label ?? null,
    notes: row.notes ?? null,
    sourceId: row.source_id ?? null,
    signedAmount: row.signed_amount ?? null,
    accountName: row.account_name ?? null,
    pending: row.pending,
  };
}

function mapDay(row: ApiCashDay) {
  return {
    date: row.date,
    day: row.day,
    weekday: row.weekday,
    isToday: row.is_today,
    isPast: row.is_past,
    events: (row.events ?? []).map(mapEvent),
    actualEvents: (row.actual_events ?? []).map(mapEvent),
    scheduledEvents: (row.scheduled_events ?? []).map(mapEvent),
    actualBalance: row.actual_balance ?? null,
    balanceBasis: row.balance_basis,
    netChange: row.net_change,
    actualChange: row.actual_change,
    scheduledChange: row.scheduled_change,
    endingBalance: row.ending_balance,
  };
}

function mapAnchor(row: ApiCashPeriod["balance_anchor"]) {
  return {
    date: row.date,
    balance: row.balance,
    checkingBalance: row.checking_balance,
    accountCount: row.account_count,
    checkingAccountCount: row.checking_account_count,
    includedAccounts: (row.included_accounts ?? []).map((account) => ({
      id: account.id,
      name: account.name,
      institution: account.institution ?? null,
      accountType: account.account_type,
      balance: account.balance,
      mask: account.mask ?? null,
      cashProjectionRole: account.cash_projection_role,
    })),
    usesCashAccounts: row.uses_cash_accounts,
  };
}

function mapGraph(row: ApiCashGraph) {
  return {
    points: row.points,
    zeroAxisPct: row.zero_axis_pct,
    showZeroLine: row.show_zero_line,
    minValue: row.min_value,
    maxValue: row.max_value,
    monthMarkers: (row.month_markers ?? []).map((marker) => ({
      label: marker.label,
      axisLabel: marker.axis_label,
      xPct: marker.x_pct,
    })),
    pointRows: (row.point_rows ?? []).map((point) => ({
      xPct: point.x_pct,
      yPct: point.y_pct,
      dateLabel: point.date_label,
      balance: point.balance,
      balanceBasis: point.balance_basis,
    })),
  };
}

function mapPeriod(row: ApiCashPeriod) {
  return {
    month: row.month,
    monthLabel: row.month_label,
    startDate: row.start_date,
    endDate: row.end_date,
    startBalance: row.start_balance,
    endBalance: row.end_balance,
    balanceAnchor: mapAnchor(row.balance_anchor),
    lowestBalance: { date: row.lowest_balance.date, balance: row.lowest_balance.balance },
    highestBalance: { date: row.highest_balance.date, balance: row.highest_balance.balance },
    days: (row.days ?? []).map(mapDay),
    weeks: (row.weeks ?? []).map((week) => ({
      weekStart: week.week_start,
      weekEnd: week.week_end,
      days: (week.days ?? []).map(mapDay),
      income: week.income,
      expenses: week.expenses,
      endingBalance: week.ending_balance,
      netChange: week.net_change,
    })),
    calendarCells: (row.calendar_cells ?? []).map((day) => day ? mapDay(day) : null),
    events: (row.events ?? []).map(mapEvent),
    trend: {
      currentVariableSpend: row.trend.current_variable_spend,
      plannedVariableSpend: row.trend.planned_variable_spend,
      averageFirstHalfShare: row.trend.average_first_half_share,
      affectsProjection: row.trend.affects_projection,
      message: row.trend.message,
    },
    graph: mapGraph(row.graph),
  };
}

export function mapCashProjectionCalendarFeed(row: ApiCalendarFeed) {
  return {
    enabled: row.enabled,
    feedUrl: row.feed_url ?? null,
    webcalUrl: row.webcal_url ?? null,
    googleUrl: row.google_url ?? null,
    generatedAt: row.generated_at ?? null,
    historyMonths: row.history_months,
  };
}

export function mapCashProjection(data: ApiCashProjection) {
  const range = data.projection_range;
  return cashProjectionViewSchema.safeParse({
    horizon: data.horizon,
    view: data.view,
    projection: mapPeriod(data.projection),
    projectionRange: {
      startMonth: range.start_month,
      startDate: range.start_date,
      endDate: range.end_date,
      months: range.months,
      projections: (range.projections ?? []).map(mapPeriod),
      days: (range.days ?? []).map(mapDay),
      events: (range.events ?? []).map(mapEvent),
      startBalance: range.start_balance,
      endBalance: range.end_balance,
      balanceAnchor: mapAnchor(range.balance_anchor),
      lowestBalance: { date: range.lowest_balance.date, balance: range.lowest_balance.balance },
      highestBalance: { date: range.highest_balance.date, balance: range.highest_balance.balance },
      graph: mapGraph(range.graph),
    },
    previousMonth: data.previous_month,
    nextMonth: data.next_month,
    customStart: data.custom_start,
    customEnd: data.custom_end,
    customMinDate: data.custom_min_date,
    customMaxDate: data.custom_max_date,
    projectionMinMonth: data.projection_min_month,
    projectionMaxMonth: data.projection_max_month,
    accountRows: (data.account_rows ?? []).map((row) => ({
      accountId: row.account_id,
      name: row.name,
      institution: row.institution ?? null,
      accountType: row.account_type,
      balance: row.balance,
      mask: row.mask ?? null,
      role: row.role,
      included: row.included,
      statusLabel: row.status_label,
      statusClass: row.status_class,
      statusDetail: row.status_detail,
    })),
    detectedRecurring: (data.detected_recurring ?? []).map((row) => ({
      detectionKey: row.detection_key,
      name: row.name,
      amount: row.amount,
      frequency: row.frequency,
      startDate: row.start_date,
      secondDayOfMonth: row.second_day_of_month ?? null,
      categoryLabel: row.category_label ?? null,
      notes: row.notes ?? null,
      lastSeen: row.last_seen,
    })),
    ignoredRecurring: (data.ignored_recurring ?? []).map((row) => ({
      id: row.id,
      detectionKey: row.detection_key,
      name: row.name,
      amount: row.amount,
      frequency: row.frequency,
      categoryLabel: row.category_label ?? null,
      lastSeen: row.last_seen ?? null,
      notes: row.notes ?? null,
    })),
    calendarFeed: mapCashProjectionCalendarFeed(data.calendar_feed),
    refresh: data.refresh ? { synced: data.refresh.synced, errors: data.refresh.errors ?? [] } : null,
  });
}
