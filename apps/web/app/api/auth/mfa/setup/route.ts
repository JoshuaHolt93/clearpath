import {
  mfaSetupConfirmRequestSchema,
  mfaSetupResultSchema,
  mfaSetupSchema,
} from "@clearpath/validation";
import { NextResponse } from "next/server";

import {
  apiErrorMessage,
  clearPathApiClient,
  forwardedSessionHeaders,
  jsonWithSessionCookie,
  MFA_EMAIL_CHALLENGE_COOKIE,
  requestCookieValue,
  setMfaEmailChallengeCookie,
} from "@/lib/server-api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const client = clearPathApiClient();
  try {
    const { data, error, response } = await client.GET("/v1/auth/mfa/setup", {
      headers: forwardedSessionHeaders(request),
    });
    if (!response.ok || !data) {
      return NextResponse.json(
        { message: apiErrorMessage(error, "Your pending MFA setup session is unavailable.") },
        { status: response.status },
      );
    }
    const setup = mfaSetupSchema.safeParse({
      subjectType: data.subject_type,
      email: data.email,
      mfaEnabled: data.mfa_enabled,
      preferredMethod: data.preferred_method,
      setupKey: data.setup_key,
      provisioningUri: data.provisioning_uri,
      mobileSetupToken: data.mobile_setup_token,
      pushAvailable: data.push_available,
      pushProvider: data.push_provider,
      pushConfigured: data.push_configured,
      sharedAccessTotpOnly: data.shared_access_totp_only,
      emailAvailable: data.email_available,
    });
    if (!setup.success) {
      return NextResponse.json({ message: "ClearPath returned invalid MFA setup data." }, { status: 502 });
    }
    const webResponse = NextResponse.json(setup.data);
    webResponse.headers.set("cache-control", "no-store");
    return webResponse;
  } catch {
    return NextResponse.json(
      { message: "ClearPath is temporarily unavailable. Please try again." },
      { status: 503 },
    );
  }
}

export async function POST(request: Request) {
  let payload: unknown;
  try {
    payload = await request.json();
  } catch {
    return NextResponse.json({ message: "Choose an MFA setup action." }, { status: 400 });
  }
  const parsed = mfaSetupConfirmRequestSchema.safeParse(payload);
  if (!parsed.success) {
    return NextResponse.json(
      { message: parsed.error.issues[0]?.message ?? "Check your MFA setup details." },
      { status: 422 },
    );
  }

  const client = clearPathApiClient();
  try {
    const { data, error, response } = await client.POST("/v1/auth/mfa/setup", {
      body: {
        ...parsed.data,
        email_challenge_token:
          parsed.data.action === "confirm_email_code"
            ? requestCookieValue(request, MFA_EMAIL_CHALLENGE_COOKIE)
            : undefined,
      },
      headers: forwardedSessionHeaders(request),
    });
    if (!response.ok || !data) {
      return NextResponse.json(
        { message: apiErrorMessage(error, "MFA setup could not be completed.") },
        { status: response.status },
      );
    }
    const result = mfaSetupResultSchema.safeParse({
      nextStep: data.next_step,
      recoveryCodes: data.recovery_codes,
    });
    if (!result.success) {
      return NextResponse.json({ message: "ClearPath returned an invalid setup result." }, { status: 502 });
    }
    const webResponse = jsonWithSessionCookie(result.data, response);
    setMfaEmailChallengeCookie(webResponse, null);
    return webResponse;
  } catch {
    return NextResponse.json(
      { message: "ClearPath is temporarily unavailable. Please try again." },
      { status: 503 },
    );
  }
}
