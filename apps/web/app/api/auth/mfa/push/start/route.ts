import { mfaPushStartSchema } from "@clearpath/validation";
import { NextResponse } from "next/server";

import { apiErrorMessage, clearPathApiClient, forwardedSessionHeaders } from "@/lib/server-api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const client = clearPathApiClient();
  try {
    const { data, error, response } = await client.POST("/v1/auth/mfa/push/start", {
      body: {},
      headers: forwardedSessionHeaders(request),
    });
    if (!response.ok || !data) {
      return NextResponse.json(
        { message: apiErrorMessage(error, "Push approval could not be started.") },
        { status: response.status },
      );
    }
    const result = mfaPushStartSchema.safeParse({
      pushAvailable: data.push_available,
      fallback: data.fallback,
      authorizationUrl: data.authorization_url,
      reason: data.reason,
    });
    if (!result.success) {
      return NextResponse.json({ message: "ClearPath returned an invalid push response." }, { status: 502 });
    }
    const webResponse = NextResponse.json(result.data);
    webResponse.headers.set("cache-control", "no-store");
    return webResponse;
  } catch {
    return NextResponse.json(
      { message: "ClearPath is temporarily unavailable. Please try again." },
      { status: 503 },
    );
  }
}
