import { mfaChallengeSchema } from "@clearpath/validation";
import { NextResponse } from "next/server";

import {
  apiErrorMessage,
  clearPathApiClient,
  forwardedSessionHeaders,
  MFA_EMAIL_CHALLENGE_COOKIE,
  requestCookieValue,
  setMfaEmailChallengeCookie,
} from "@/lib/server-api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const client = clearPathApiClient();
  const emailChallengeToken = requestCookieValue(request, MFA_EMAIL_CHALLENGE_COOKIE);

  try {
    const { data, error, response } = await client.GET("/v1/auth/mfa/challenge", {
      headers: forwardedSessionHeaders(request),
      params: {
        query: {
          email_challenge_token: emailChallengeToken ?? undefined,
        },
      },
    });
    if (!response.ok || !data) {
      return NextResponse.json(
        { message: apiErrorMessage(error, "Your pending sign-in session is unavailable.") },
        { status: response.status },
      );
    }

    const challenge = mfaChallengeSchema.safeParse({
      subjectType: data.subject_type,
      email: data.email,
      preferredMethod: data.preferred_method,
      pushAvailable: data.push_available,
      emailAvailable: data.email_available,
      emailChallengeSent: data.email_challenge_sent,
    });
    if (!challenge.success) {
      return NextResponse.json(
        { message: "ClearPath returned an invalid MFA challenge." },
        { status: 502 },
      );
    }

    const webResponse = NextResponse.json(challenge.data);
    webResponse.headers.set("cache-control", "no-store");
    setMfaEmailChallengeCookie(webResponse, data.email_challenge_token);
    return webResponse;
  } catch {
    return NextResponse.json(
      { message: "ClearPath is temporarily unavailable. Please try again." },
      { status: 503 },
    );
  }
}
