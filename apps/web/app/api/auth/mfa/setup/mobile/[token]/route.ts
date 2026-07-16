import { mfaMobileSetupSchema } from "@clearpath/validation";
import { NextResponse } from "next/server";

import { apiErrorMessage, clearPathApiClient } from "@/lib/server-api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(_request: Request, context: { params: Promise<{ token: string }> }) {
  const { token } = await context.params;
  const client = clearPathApiClient();
  try {
    const { data, error, response } = await client.GET("/v1/auth/mfa/setup/mobile/{token}", {
      params: { path: { token } },
    });
    if (!response.ok || !data) {
      return NextResponse.json(
        {
          message: apiErrorMessage(error, "This MFA setup link is expired or invalid."),
          expired: response.status === 410,
        },
        { status: response.status },
      );
    }
    const result = mfaMobileSetupSchema.safeParse({
      provisioningUri: data.provisioning_uri,
      expired: data.expired,
      email: data.email,
      subjectType: data.subject_type,
    });
    if (!result.success) {
      return NextResponse.json({ message: "ClearPath returned invalid mobile setup data." }, { status: 502 });
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
