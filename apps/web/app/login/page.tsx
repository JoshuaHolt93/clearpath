import type { Metadata } from "next";
import Link from "next/link";

import { PublicAuthShell } from "../public-auth-shell";
import { LoginForm } from "./login-form";

export const metadata: Metadata = {
  title: "Sign In - ClearPath Finance",
};

type LoginPageProps = {
  searchParams: Promise<{ password_reset?: string }>;
};

export default async function LoginPage({ searchParams }: LoginPageProps) {
  const { password_reset: passwordReset } = await searchParams;
  return (
    <PublicAuthShell headingId="login-title" title="Welcome Back" subtitle="Sign in to check your finances.">
      {passwordReset === "1" ? (
        <div className="alert alert-info" role="status">Password reset. Sign in with your new password.</div>
      ) : null}
      <LoginForm />
      <p className="auth-footnote"><Link href="/forgot-password">Forgot Password?</Link></p>
      <p className="auth-footnote">
        Don&apos;t Have An Account? <Link href="/register">Create One</Link>
      </p>
      <div className="divider" role="presentation" />
      <p className="auth-demo">
        Demo: <strong>demo@clearpath.local</strong> / <strong>SampleVault123!</strong>
      </p>
    </PublicAuthShell>
  );
}
