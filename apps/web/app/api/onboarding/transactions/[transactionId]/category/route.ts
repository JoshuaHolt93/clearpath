import { onboardingCategorySelectionSchema } from "@clearpath/validation";
import { NextResponse } from "next/server";

import { apiErrorMessage, clearPathApiClient, forwardedSessionHeaders } from "@/lib/server-api";

type RouteContext = { params: Promise<{ transactionId: string }> };

export async function PATCH(request: Request, context: RouteContext) {
  const { transactionId } = await context.params;
  const parsedId = Number(transactionId);
  if (!Number.isInteger(parsedId) || parsedId <= 0) {
    return NextResponse.json({ message: "Transaction not found." }, { status: 404 });
  }
  const parsed = onboardingCategorySelectionSchema.safeParse(await request.json().catch(() => null));
  if (!parsed.success) {
    return NextResponse.json({ message: parsed.error.issues[0]?.message ?? "Choose a category." }, { status: 422 });
  }
  try {
    const { data, error, response } = await clearPathApiClient().PATCH("/v1/transactions/{transaction_id}/category", {
      params: { path: { transaction_id: parsedId } },
      body: {
        category_id: parsed.data.category_id,
        apply_to_similar: false,
        mark_recurring: false,
        recurring_frequency: "monthly",
      },
      headers: forwardedSessionHeaders(request),
    });
    if (!response.ok || !data) {
      return NextResponse.json(
        { message: apiErrorMessage(error, "We could not update that transaction category.") },
        { status: response.status },
      );
    }
    return NextResponse.json({ transactionId: data.transaction.id, categoryId: data.transaction.category?.id ?? null });
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}
