import type { Metadata } from "next";
import Link from "next/link";

import { LoginForm } from "./login-form";

export const metadata: Metadata = {
  title: "Sign In - ClearPath Finance",
};

export default function LoginPage() {
  return (
    <>
      <main className="auth-page">
        <div className="auth-wrap">
          <section className="auth-card" aria-labelledby="login-title">
            <Link href="/" className="auth-logo" aria-label="ClearPath Finance home">
              <span className="logo-mark" aria-hidden="true">C</span>
              <span className="auth-logo-text">
                <span className="name">ClearPath</span>
                <span className="sub">Finance</span>
              </span>
            </Link>
            <h1 className="auth-title" id="login-title">Welcome Back</h1>
            <p className="auth-subtitle">Sign in to check your finances.</p>

            <LoginForm />

            <p className="auth-footnote"><Link href="/forgot-password">Forgot Password?</Link></p>
            <p className="auth-footnote">
              Don&apos;t Have An Account? <Link href="/register">Create One</Link>
            </p>
            <div className="divider" role="presentation" />
            <p className="auth-demo">
              Demo: <strong>demo@clearpath.local</strong> / <strong>SampleVault123!</strong>
            </p>
          </section>
        </div>
      </main>
      <footer className="public-policy-footer">
        <Link href="/pricing">Pricing</Link>
        <Link href="/privacy">Privacy Policy</Link>
        <Link href="/terms">Terms &amp; Conditions</Link>
        <Link href="/ethics">Ethics Policy</Link>
        <a href="mailto:clearpathfinance1@proton.me">Contact: clearpathfinance1@proton.me</a>
      </footer>
    </>
  );
}
