import type { Metadata } from "next";
import Link from "next/link";

import { PublicAuthShell } from "../public-auth-shell";
import { ForgotPasswordForm } from "./forgot-password-form";

export const metadata: Metadata = { title: "Reset Password - ClearPath Finance" };

export default function ForgotPasswordPage() {
  return (
    <PublicAuthShell
      headingId="forgot-password-title"
      title="Reset Password"
      subtitle="Enter your email and ClearPath will send a reset link if the account exists."
    >
      <ForgotPasswordForm />
      <p className="auth-footnote"><Link href="/login">Back To Sign In</Link></p>
    </PublicAuthShell>
  );
}
