import type { Metadata } from "next";

import { PublicAuthShell } from "../../public-auth-shell";
import { ResetPasswordForm } from "./reset-password-form";

export const metadata: Metadata = { title: "Choose New Password - ClearPath Finance" };

export default async function ResetPasswordPage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  return (
    <PublicAuthShell
      headingId="reset-password-title"
      title="Choose New Password"
      subtitle="Use a strong password you have not used on another site."
    >
      <ResetPasswordForm token={token} />
    </PublicAuthShell>
  );
}
