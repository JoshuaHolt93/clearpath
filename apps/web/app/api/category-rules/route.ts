import { categoryRuleMutationInputSchema } from "@clearpath/validation";
import { NextResponse } from "next/server";

import { mapCategoryRules } from "@/lib/category-rules";
import { apiErrorMessage, clearPathApiClient, forwardedSessionHeaders } from "@/lib/server-api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function apiConditions(conditions: Array<{ field: string; operator: string; value: string; valueSecondary: string; group: string; join: string }>) {
  return conditions.map((condition) => ({
    field: condition.field,
    operator: condition.operator,
    value: condition.value,
    value_secondary: condition.valueSecondary,
    group: condition.group,
    join: condition.join,
  }));
}

export async function GET(request: Request) {
  const headers = forwardedSessionHeaders(request);
  try {
    const [rules, me] = await Promise.all([
      clearPathApiClient().GET("/v1/category-rules", { headers }),
      clearPathApiClient().GET("/v1/me", { headers }),
    ]);
    if (!rules.response.ok || !rules.data) return NextResponse.json({ message: apiErrorMessage(rules.error, "We could not load categorization rules.") }, { status: rules.response.status });
    if (!me.response.ok || !me.data) return NextResponse.json({ message: apiErrorMessage(me.error, "We could not load your session.") }, { status: me.response.status });
    const mapped = mapCategoryRules(rules.data, me.data);
    if (!mapped.success) return NextResponse.json({ message: "Categorization rule data did not match the expected contract." }, { status: 502 });
    return NextResponse.json(mapped.data, { headers: { "cache-control": "no-store" } });
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}

export async function POST(request: Request) {
  const parsed = categoryRuleMutationInputSchema.safeParse(await request.json().catch(() => null));
  if (!parsed.success) return NextResponse.json({ message: parsed.error.issues[0]?.message ?? "Check the rule conditions." }, { status: 422 });
  try {
    const { data, error, response } = await clearPathApiClient().POST("/v1/category-rules", {
      body: { category_id: parsed.data.categoryId, conditions: apiConditions(parsed.data.conditions), match_text: null },
      headers: forwardedSessionHeaders(request),
    });
    if (!response.ok || !data) return NextResponse.json({ message: apiErrorMessage(error, "We could not create that rule.") }, { status: response.status });
    return NextResponse.json({ ruleId: data.id, appliedCount: data.applied_count ?? 0 }, { status: 201 });
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}
