import type { Metadata } from "next";
import Link from "next/link";

import { PublicAuthShell } from "../public-auth-shell";
import { RegisterForm } from "./register-form";

export const metadata: Metadata = { title: "Create Account - ClearPath Finance" };

export default function RegisterPage() {
  return (
    <PublicAuthShell
      headingId="register-title"
      title="Create Your Account"
      subtitle="Set up your monthly baseline in a few minutes."
    >
      <RegisterForm />
      <p className="auth-footnote">Already Have An Account? <Link href="/login">Sign In</Link></p>
    </PublicAuthShell>
  );
}
