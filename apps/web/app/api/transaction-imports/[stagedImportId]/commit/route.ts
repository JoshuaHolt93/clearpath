import { NextResponse } from "next/server";

import { apiErrorMessage, clearPathApiClient, forwardedSessionHeaders } from "@/lib/server-api";

type Context = { params: Promise<{ stagedImportId: string }> };

export async function POST(request: Request, context: Context) {
  const stagedImportId = (await context.params).stagedImportId;
  if (!stagedImportId) return NextResponse.json({ message: "Import preview not found." }, { status: 404 });
  try {
    const { data, error, response } = await clearPathApiClient().POST("/v1/transaction-imports/{staged_import_id}/commit", {
      params: { path: { staged_import_id: stagedImportId } }, body: { confirm: true }, headers: forwardedSessionHeaders(request),
    });
    if (!response.ok || !data) return NextResponse.json({ message: apiErrorMessage(error, "We could not import those transactions.") }, { status: response.status });
    return NextResponse.json({ imported: data.imported, duplicateCount: data.duplicate_count });
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}
