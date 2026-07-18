import { categoryCreateInputSchema } from "@clearpath/validation";
import { NextResponse } from "next/server";

import { apiErrorMessage, clearPathApiClient, forwardedSessionHeaders } from "@/lib/server-api";

export async function POST(request: Request) {
  const parsed = categoryCreateInputSchema.safeParse(await request.json().catch(() => null));
  if (!parsed.success) return NextResponse.json({ message: parsed.error.issues[0]?.message ?? "Check the category details." }, { status: 422 });
  try {
    const { data, error, response } = await clearPathApiClient().POST("/v1/categories", { body: { name: parsed.data.name, kind: parsed.data.kind, activate_budget: parsed.data.activateBudget }, headers: forwardedSessionHeaders(request) });
    if (!response.ok || !data) return NextResponse.json({ message: apiErrorMessage(error, "We could not create that category.") }, { status: response.status });
    return NextResponse.json({ categoryId: data.id, name: data.name }, { status: 201 });
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}
