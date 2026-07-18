import { subscriptionImportInputSchema } from "@clearpath/validation";
import { NextResponse } from "next/server";

import { apiErrorMessage, clearPathApiClient, forwardedSessionHeaders } from "@/lib/server-api";

export async function POST(request: Request) {
  const parsed = subscriptionImportInputSchema.safeParse(await request.json().catch(() => null));
  if (!parsed.success) return NextResponse.json({ message: parsed.error.issues[0]?.message ?? "Choose a CSV file to scan." }, { status: 422 });
  try {
    const { data, error, response } = await clearPathApiClient().POST("/v1/subscription-imports", {
      body: { csv_text: parsed.data.csvText, csv_base64: null }, headers: forwardedSessionHeaders(request),
    });
    if (!response.ok || !data) return NextResponse.json({ message: apiErrorMessage(error, "We could not import that CSV.") }, { status: response.status });
    return NextResponse.json({ imported: data.imported, syncedCount: data.synced_count });
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}
