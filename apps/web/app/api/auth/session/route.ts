import { NextResponse } from "next/server";

import {
  apiErrorMessage,
  clearPathApiClient,
  forwardedSessionHeaders,
  jsonWithSessionCookie,
} from "@/lib/server-api";

export async function DELETE(request: Request) {
  try {
    const { data, error, response } = await clearPathApiClient().DELETE("/v1/auth/session", {
      body: { everywhere: false },
      headers: forwardedSessionHeaders(request),
    });
    if (!response.ok || !data) {
      return NextResponse.json(
        { message: apiErrorMessage(error, "We could not sign you out.") },
        { status: response.status },
      );
    }
    return jsonWithSessionCookie({ ok: data.ok }, response);
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}
