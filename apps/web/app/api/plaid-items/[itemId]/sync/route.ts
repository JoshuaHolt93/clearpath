import { NextResponse } from "next/server";

import { apiErrorMessage, clearPathApiClient, forwardedSessionHeaders } from "@/lib/server-api";

type Context = { params: Promise<{ itemId: string }> };

export async function POST(request: Request, context: Context) {
  const itemId = Number((await context.params).itemId);
  if (!Number.isInteger(itemId) || itemId < 1) return NextResponse.json({ message: "Connected institution not found." }, { status: 404 });
  try {
    const { data, error, response } = await clearPathApiClient().POST("/v1/plaid-items/{item_id}/sync", { params: { path: { item_id: itemId } }, headers: forwardedSessionHeaders(request) });
    if (!response.ok || !data) return NextResponse.json({ message: apiErrorMessage(error, "We could not sync that institution.") }, { status: response.status });
    return NextResponse.json({ added: data.added, modified: data.modified, removed: data.removed });
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}
