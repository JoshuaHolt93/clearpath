import {
  accountDeleteInputSchema,
  householdNameInputSchema,
  mfaPreferenceInputSchema,
  passwordChangeInputSchema,
} from "@clearpath/validation";
import { NextResponse } from "next/server";

import { apiErrorMessage, clearPathApiClient, forwardedSessionHeaders } from "@/lib/server-api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// One mutation surface for the account-level settings actions; the `action`
// discriminator mirrors Flask's settings form actions.
export async function POST(request: Request) {
  const body = (await request.json().catch(() => null)) as { action?: string } | null;
  const headers = forwardedSessionHeaders(request);
  const client = clearPathApiClient();

  try {
    if (body?.action === "password") {
      const parsed = passwordChangeInputSchema.safeParse(body);
      if (!parsed.success) return NextResponse.json({ message: parsed.error.issues[0]?.message ?? "Check the password fields." }, { status: 422 });
      const { data, error, response } = await client.PATCH("/v1/me/password", {
        headers,
        body: { current_password: parsed.data.currentPassword, new_password: parsed.data.newPassword, confirm_password: parsed.data.confirmPassword },
      });
      if (!response.ok || !data) return NextResponse.json({ message: apiErrorMessage(error, "We could not update the password.") }, { status: response.status });
      return NextResponse.json({ updated: true, message: "Password updated." });
    }
    if (body?.action === "household") {
      const parsed = householdNameInputSchema.safeParse(body);
      if (!parsed.success) return NextResponse.json({ message: "Check the household name." }, { status: 422 });
      const { data, error, response } = await client.PATCH("/v1/households/current", { headers, body: { household_name: parsed.data.householdName } });
      if (!response.ok || !data) return NextResponse.json({ message: apiErrorMessage(error, "We could not update the household.") }, { status: response.status });
      return NextResponse.json({ householdName: data.household_name ?? null, message: "Household settings updated." });
    }
    if (body?.action === "mfa_preferences") {
      const parsed = mfaPreferenceInputSchema.safeParse(body);
      if (!parsed.success) return NextResponse.json({ message: "Choose an MFA method." }, { status: 422 });
      const { data, error, response } = await client.PATCH("/v1/auth/mfa/preferences", { headers, body: { mfa_preferred_method: parsed.data.mfaPreferredMethod } });
      if (!response.ok || !data) return NextResponse.json({ message: apiErrorMessage(error, "We could not update MFA preferences.") }, { status: response.status });
      return NextResponse.json({ mfaPreferredMethod: data.mfa_preferred_method, mfaPushEnabled: data.mfa_push_enabled, message: data.message });
    }
    if (body?.action === "ethics") {
      const { data, error, response } = await client.POST("/v1/me/compliance-acknowledgements/ethics", { headers, body: { acknowledged: true } });
      if (!response.ok || !data) return NextResponse.json({ message: apiErrorMessage(error, "We could not record the acknowledgement.") }, { status: response.status });
      return NextResponse.json({
        ethicsAcknowledgedAt: data.ethics_acknowledged_at,
        ethicsPolicyVersion: data.ethics_policy_version,
        message: "Thank you for acknowledging the ClearPath Ethics, Terms, and Privacy Policy.",
      });
    }
    if (body?.action === "account_delete") {
      const parsed = accountDeleteInputSchema.safeParse(body);
      if (!parsed.success) return NextResponse.json({ message: parsed.error.issues[0]?.message ?? "Check the deletion fields." }, { status: 422 });
      const { data, error, response } = await client.DELETE("/v1/me/account", {
        headers,
        body: { current_password: parsed.data.currentPassword, confirmation: parsed.data.confirmation },
      });
      if (!response.ok || !data) return NextResponse.json({ message: apiErrorMessage(error, "We could not delete the account.") }, { status: response.status });
      return NextResponse.json({ deleted: true, message: "Your ClearPath account and app data were deleted." });
    }
    return NextResponse.json({ message: "Unknown settings action." }, { status: 422 });
  } catch {
    return NextResponse.json({ message: "ClearPath is temporarily unavailable. Please try again." }, { status: 503 });
  }
}
