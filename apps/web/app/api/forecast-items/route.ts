import { forecastItemInputSchema } from "@clearpath/validation";
import { NextResponse } from "next/server";

import { apiErrorMessage, clearPathApiClient, forwardedSessionHeaders } from "@/lib/server-api";

export const runtime = "nodejs";

function bodyFor(value: ReturnType<typeof forecastItemInputSchema.parse>) {
  return {
    item_date: value.itemDate, description: value.description, amount: value.amount,
    item_type: value.itemType, category_label: value.categoryLabel, notes: value.notes,
  };
}

export async function POST(request: Request) {
  const parsed = forecastItemInputSchema.safeParse(await request.json().catch(() => null));
  if (!parsed.success) return NextResponse.json({ message: parsed.error.issues[0]?.message ?? "Check the one-time expense details." }, { status: 422 });
  try {
    const { data, error, response } = await clearPathApiClient().POST("/v1/forecast-items", {
      body: bodyFor(parsed.data), headers: forwardedSessionHeaders(request),
    });
    if (!response.ok || !data) return NextResponse.json({ message: apiErrorMessage(error, "We could not add that one-time expense.") }, { status: response.status });
    return NextResponse.json({ itemId: data.id, description: data.description, amount: data.amount }, { status: 201 });
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}
