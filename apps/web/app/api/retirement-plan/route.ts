import { retirementSurveyInputSchema, retirementWorksheetInputSchema } from "@clearpath/validation";
import { NextResponse } from "next/server";

import { mapRetirement } from "@/lib/retirement";
import { apiErrorMessage, clearPathApiClient, forwardedSessionHeaders } from "@/lib/server-api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

async function loadAndMap(request: Request) {
  const headers = forwardedSessionHeaders(request);
  const client = clearPathApiClient();
  const [plan, me] = await Promise.all([
    client.GET("/v1/retirement-plan", { headers }),
    client.GET("/v1/me", { headers }),
  ]);
  if (!plan.response.ok || !plan.data) return { error: NextResponse.json({ message: apiErrorMessage(plan.error, "We could not load your retirement plan.") }, { status: plan.response.status }) };
  if (!me.response.ok || !me.data) return { error: NextResponse.json({ message: apiErrorMessage(me.error, "We could not load your session.") }, { status: me.response.status }) };
  const mapped = mapRetirement(plan.data, me.data);
  if (!mapped.success) return { error: NextResponse.json({ message: "Retirement data did not match the expected contract." }, { status: 502 }) };
  return { data: mapped.data };
}

export async function GET(request: Request) {
  try {
    const result = await loadAndMap(request);
    if (result.error) return result.error;
    return NextResponse.json(result.data, { headers: { "cache-control": "no-store" } });
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}

export async function PATCH(request: Request) {
  const body = (await request.json().catch(() => null)) as { section?: string } | null;
  const headers = forwardedSessionHeaders(request);
  const client = clearPathApiClient();
  try {
    if (body?.section === "worksheet") {
      const parsed = retirementWorksheetInputSchema.safeParse(body);
      if (!parsed.success) return NextResponse.json({ message: "Check the worksheet notes." }, { status: 422 });
      const { data, error, response } = await client.PATCH("/v1/retirement-plan/worksheet", {
        headers,
        body: {
          retirement_lifestyle_notes: parsed.data.retirementLifestyleNotes,
          retirement_location_notes: parsed.data.retirementLocationNotes,
          retirement_healthcare_notes: parsed.data.retirementHealthcareNotes,
          retirement_income_notes: parsed.data.retirementIncomeNotes,
          retirement_debt_notes: parsed.data.retirementDebtNotes,
          retirement_family_notes: parsed.data.retirementFamilyNotes,
        },
      });
      if (!response.ok || !data) return NextResponse.json({ message: apiErrorMessage(error, "We could not save the worksheet.") }, { status: response.status });
    } else {
      const parsed = retirementSurveyInputSchema.safeParse(body);
      if (!parsed.success) return NextResponse.json({ message: "Check the retirement details." }, { status: 422 });
      const { data, error, response } = await client.PATCH("/v1/retirement-plan", {
        headers,
        body: {
          retirement_enabled: parsed.data.retirementEnabled,
          retirement_has_employer_plan: parsed.data.retirementHasEmployerPlan,
          retirement_employer_withheld: parsed.data.retirementEmployerWithheld,
          retirement_has_personal_plan: parsed.data.retirementHasPersonalPlan,
          retirement_monthly_contribution: parsed.data.retirementMonthlyContribution,
          retirement_personal_monthly_contribution: parsed.data.retirementPersonalMonthlyContribution,
        },
      });
      if (!response.ok || !data) return NextResponse.json({ message: apiErrorMessage(error, "We could not save the retirement plan.") }, { status: response.status });
    }
    const result = await loadAndMap(request);
    if (result.error) return result.error;
    return NextResponse.json(result.data, { headers: { "cache-control": "no-store" } });
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}
