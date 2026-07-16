import { registerRequestSchema, registerResultSchema } from "@clearpath/validation";
import { NextResponse } from "next/server";

import { apiErrorMessage, clearPathApiClient, jsonWithSessionCookie } from "@/lib/server-api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  let payload: unknown;
  try {
    payload = await request.json();
  } catch {
    return NextResponse.json({ message: "Complete the account form to continue." }, { status: 400 });
  }
  const parsed = registerRequestSchema.safeParse(payload);
  if (!parsed.success) {
    return NextResponse.json(
      { message: parsed.error.issues[0]?.message ?? "Check your account details." },
      { status: 422 },
    );
  }
  try {
    const { data, error, response } = await clearPathApiClient().POST("/v1/auth/register", {
      body: {
        ...parsed.data,
        ethics_acknowledgement: false,
        legal_acknowledgement: false,
      },
    });
    if (!response.ok || !data) {
      return NextResponse.json(
        { message: apiErrorMessage(error, "We could not create your account. Please try again.") },
        { status: response.status },
      );
    }
    const result = registerResultSchema.safeParse({ nextStep: data.next_step });
    if (!result.success) {
      return NextResponse.json({ message: "ClearPath returned an invalid account destination." }, { status: 502 });
    }
    return jsonWithSessionCookie(result.data, response, { status: 201 });
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}
