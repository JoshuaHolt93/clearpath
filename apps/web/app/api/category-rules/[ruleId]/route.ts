import { categoryRuleDeleteInputSchema, categoryRuleMutationInputSchema } from "@clearpath/validation";
import { NextResponse } from "next/server";

import { apiErrorMessage, clearPathApiClient, forwardedSessionHeaders } from "@/lib/server-api";

type Context = { params: Promise<{ ruleId: string }> };
const readRuleId = async (context: Context) => Number((await context.params).ruleId);

function apiConditions(conditions: Array<{ field: string; operator: string; value: string; valueSecondary: string; group: string; join: string }>) {
  return conditions.map((condition) => ({ field: condition.field, operator: condition.operator, value: condition.value, value_secondary: condition.valueSecondary, group: condition.group, join: condition.join }));
}

export async function PATCH(request: Request, context: Context) {
  const id = await readRuleId(context);
  if (!Number.isInteger(id) || id < 1) return NextResponse.json({ message: "Rule not found." }, { status: 404 });
  const parsed = categoryRuleMutationInputSchema.safeParse(await request.json().catch(() => null));
  if (!parsed.success) return NextResponse.json({ message: parsed.error.issues[0]?.message ?? "Check the rule conditions." }, { status: 422 });
  try {
    const { data, error, response } = await clearPathApiClient().PATCH("/v1/category-rules/{rule_id}", {
      params: { path: { rule_id: id } },
      body: { category_id: parsed.data.categoryId, conditions: apiConditions(parsed.data.conditions), match_text: null },
      headers: forwardedSessionHeaders(request),
    });
    if (!response.ok || !data) return NextResponse.json({ message: apiErrorMessage(error, "We could not update that rule.") }, { status: response.status });
    return NextResponse.json({ ruleId: data.id, appliedCount: data.applied_count ?? 0 });
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}

export async function DELETE(request: Request, context: Context) {
  const id = await readRuleId(context);
  if (!Number.isInteger(id) || id < 1) return NextResponse.json({ message: "Rule not found." }, { status: 404 });
  const parsed = categoryRuleDeleteInputSchema.safeParse(await request.json().catch(() => null));
  if (!parsed.success) return NextResponse.json({ message: "Confirm rule deletion." }, { status: 422 });
  try {
    const { data, error, response } = await clearPathApiClient().DELETE("/v1/category-rules/{rule_id}", {
      params: { path: { rule_id: id } },
      body: { confirm: true },
      headers: forwardedSessionHeaders(request),
    });
    if (!response.ok || !data) return NextResponse.json({ message: apiErrorMessage(error, "We could not delete that rule.") }, { status: response.status });
    return NextResponse.json({ deletedRuleId: id });
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}
