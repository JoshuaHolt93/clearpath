import { NextResponse } from "next/server";

import { mapSettings } from "@/lib/settings";
import { apiErrorMessage, clearPathApiClient, forwardedSessionHeaders } from "@/lib/server-api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const headers = forwardedSessionHeaders(request);
  try {
    const [settings, me] = await Promise.all([
      clearPathApiClient().GET("/v1/me/settings", { headers }),
      clearPathApiClient().GET("/v1/me", { headers }),
    ]);
    if (!settings.response.ok || !settings.data) return NextResponse.json({ message: apiErrorMessage(settings.error, "We could not load settings.") }, { status: settings.response.status });
    if (!me.response.ok || !me.data) return NextResponse.json({ message: apiErrorMessage(me.error, "We could not load your session.") }, { status: me.response.status });
    const mapped = mapSettings(settings.data, me.data);
    if (!mapped.success) return NextResponse.json({ message: "Settings data did not match the expected contract." }, { status: 502 });
    return NextResponse.json(mapped.data, { headers: { "cache-control": "no-store" } });
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}
