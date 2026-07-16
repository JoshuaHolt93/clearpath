"use client";

import { loginResultSchema } from "@clearpath/validation";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { AUTH_NEXT_STEP_PATHS } from "@/lib/auth-navigation";

export function PushCallbackPanel() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    async function completePush() {
      try {
        const response = await fetch(`/api/auth/mfa/push/callback${window.location.search}`, { cache: "no-store" });
        const payload: unknown = await response.json();
        if (!response.ok) {
          const message = payload && typeof payload === "object" && "message" in payload
            ? String((payload as { message: unknown }).message)
            : "Push approval was not completed.";
          throw new Error(message);
        }
        const result = loginResultSchema.safeParse(payload);
        if (!result.success) {
          throw new Error("ClearPath returned an unexpected sign-in response.");
        }
        router.replace(AUTH_NEXT_STEP_PATHS[result.data.nextStep]);
        router.refresh();
      } catch (callbackError) {
        if (active) {
          setError(callbackError instanceof Error ? callbackError.message : "Push approval was not completed.");
        }
      }
    }
    void completePush();
    return () => {
      active = false;
    };
  }, [router]);

  if (!error) {
    return <p className="pending-status" role="status">Confirming push approval...</p>;
  }
  return (
    <>
      <div className="alert alert-error" role="alert">{error}</div>
      <p className="panel-footnote"><Link href="/mfa/verify">Use An Authenticator Code</Link></p>
    </>
  );
}
