import type { components } from "@clearpath/api-client";
import {
  onboardingIncomePlanRequestSchema,
  onboardingStatusSchema,
} from "@clearpath/validation";
import { NextResponse } from "next/server";

import {
  apiErrorMessage,
  clearPathApiClient,
  forwardedSessionHeaders,
} from "@/lib/server-api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type ApiStatus = components["schemas"]["OnboardingStatusResponse"];

function mapStatus(data: ApiStatus) {
  const profile = data.profile;
  const result = onboardingStatusSchema.safeParse({
    activeStep: data.active_step,
    incomeReady: data.income_ready,
    hasBank: data.has_bank,
    setupComplete: data.setup_complete,
    profile: {
      householdName: profile.household_name ?? null,
      incomeAmount: profile.income_amount ?? null,
      incomeAmountDisplay: profile.income_amount_display ?? null,
      monthlyIncome: profile.monthly_income ?? null,
      incomeBasis: profile.income_basis ?? null,
      incomeType: profile.income_type ?? null,
      paycheckCadence: profile.paycheck_cadence ?? null,
      nextPayDate: profile.next_pay_date ?? null,
      paycheckSecondDate: profile.paycheck_second_date ?? null,
      paycheckDaysOfWeek: profile.paycheck_days_of_week ?? null,
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
    today: data.today,
    plaidStatus: {
      ready: data.plaid_status.ready,
      sdkInstalled: data.plaid_status.sdk_installed,
      cryptoInstalled: data.plaid_status.crypto_installed,
      hasCredentials: data.plaid_status.has_credentials,
      hasEncryptionKey: data.plaid_status.has_encryption_key,
      environment: data.plaid_status.environment,
    },
    plaidItems: (data.plaid_items ?? []).map((item) => ({
      id: item.id,
      institutionName: item.institution_name ?? null,
      status: item.status,
      lastSyncedAt: item.last_synced_at ?? null,
    })),
    transactions: (data.transactions ?? []).map((transaction) => ({
      id: transaction.id,
      displayMerchant: transaction.display_merchant,
      postedDate: transaction.posted_date,
      amount: transaction.amount,
      accountName: transaction.account_name ?? null,
      sourceName: transaction.source_name ?? null,
      categoryId: transaction.category_id ?? null,
    })),
    categories: data.categories ?? [],
    autoCategorizedCount: data.auto_categorized_count,
    seededBudgetCount: data.seeded_budget_count,
    message: data.message ?? null,
    nextPath: data.next_path ?? null,
    incomeBasisOptions: data.income_basis_options,
    incomeTypeOptions: data.income_type_options,
    paycheckCadenceOptions: data.paycheck_cadence_options,
    recurringFrequencyOptions: data.recurring_frequency_options,
    weekdayOptions: data.weekday_options,
    monthlyWeekOptions: data.monthly_week_options,
    taxFilingStatusOptions: data.tax_filing_status_options,
    stateOptions: data.state_options,
  });
  return result.success ? result.data : null;
}

function statusResponse(data: ApiStatus | undefined, error: unknown, response: Response) {
  if (!response.ok || !data) {
    return NextResponse.json(
      { message: apiErrorMessage(error, "We could not load your setup progress.") },
      { status: response.status },
    );
  }
  const mapped = mapStatus(data);
  if (!mapped) {
    return NextResponse.json({ message: "ClearPath returned invalid setup details." }, { status: 502 });
  }
  return NextResponse.json(mapped, { headers: { "cache-control": "no-store" } });
}

export async function GET(request: Request) {
  const step = new URL(request.url).searchParams.get("step") ?? "";
  try {
    const { data, error, response } = await clearPathApiClient().GET("/v1/onboarding/status", {
      params: { query: { step } },
      headers: forwardedSessionHeaders(request),
    });
    return statusResponse(data, error, response);
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}

export async function PATCH(request: Request) {
  const payload = await request.json().catch(() => null);
  const parsed = onboardingIncomePlanRequestSchema.safeParse(payload);
  if (!parsed.success) {
    return NextResponse.json(
      { message: parsed.error.issues[0]?.message ?? "Check your income details." },
      { status: 422 },
    );
  }
  try {
    const { data, error, response } = await clearPathApiClient().PATCH("/v1/onboarding/income-plan", {
      body: parsed.data,
      headers: forwardedSessionHeaders(request),
    });
    return statusResponse(data, error, response);
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}

export async function POST(request: Request) {
  try {
    const { data, error, response } = await clearPathApiClient().POST("/v1/onboarding/complete", {
      body: { confirm: true },
      headers: forwardedSessionHeaders(request),
    });
    return statusResponse(data, error, response);
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}
