import { loginResultSchema } from "@clearpath/validation";
import { NextResponse } from "next/server";

import {
  apiErrorMessage,
  clearPathApiClient,
  forwardedSessionHeaders,
  jsonWithSessionCookie,
} from "@/lib/server-api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const url = new URL(request.url);
  const client = clearPathApiClient();
  try {
    const { data, error, response } = await client.GET("/v1/auth/mfa/push/callback", {
      headers: forwardedSessionHeaders(request),
      params: {
        query: {
          state: url.searchParams.get("state") ?? undefined,
          duo_code: url.searchParams.get("duo_code") ?? undefined,
        },
      },
    });
    if (!response.ok || !data) {
      return NextResponse.json(
        { message: apiErrorMessage(error, "Push approval was not completed.") },
        { status: response.status },
      );
    }
    const result = loginResultSchema.safeParse({ nextStep: data.next_step });
    if (!result.success) {
      return NextResponse.json({ message: "ClearPath returned an invalid sign-in destination." }, { status: 502 });
    }
    return jsonWithSessionCookie(result.data, response);
  } catch {
    return NextResponse.json(
      { message: "ClearPath is temporarily unavailable. Please try again." },
      { status: 503 },
    );
  }
}
