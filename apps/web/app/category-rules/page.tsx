import type { Metadata } from "next";

import { CategoryRulesWorkspace, type RulePrefill } from "./category-rules-workspace";

export const metadata: Metadata = { title: "Categorization Rules | ClearPath Finance" };

function value(raw: string | string[] | undefined, fallback = "") {
  return Array.isArray(raw) ? raw[0] ?? fallback : raw ?? fallback;
}

export default async function CategoryRulesPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const params = await searchParams;
  const fields = new Set(["description", "account", "amount", "category"]);
  const operators = new Set(["contains", "equals", "starts_with", "ends_with", "not_contains", "gt", "gte", "lt", "lte", "between"]);
  const rawCategoryId = Number(value(params.category_id));
  const field = value(params.condition_field, "description");
  const operator = value(params.condition_operator, "contains");
  const prefill: RulePrefill = {
    field: fields.has(field) ? field : "description",
    operator: operators.has(operator) ? operator : "contains",
    value: value(params.condition_value, value(params.match_text)).trim(),
    categoryId: Number.isInteger(rawCategoryId) && rawCategoryId > 0 ? rawCategoryId : null,
  };
  return <CategoryRulesWorkspace prefill={prefill} />;
}
