import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { apiErrorMessage, clearPathClient } from "./api";
import { clearSessionToken, loadSessionToken, saveSessionToken } from "./session-store";

// The next step the API wants after a successful password check. Mirrors the
// FastAPI AuthLoginResponse.next_step enum so the router can send the user to
// the right place (MFA, plan selection, onboarding, or the dashboard).
export type NextStep = "mfa_verify" | "mfa_setup" | "select_plan" | "onboarding" | "dashboard";

export type SessionUser = {
  id: number;
  email: string;
  displayName: string;
  primaryAccountHolder: boolean;
};

type AuthState = {
  status: "loading" | "signedOut" | "signedIn";
  user: SessionUser | null;
};

type AuthContextValue = AuthState & {
  signIn: (email: string, password: string, staySignedIn: boolean) => Promise<{ nextStep: NextStep }>;
  signOut: () => Promise<void>;
  refresh: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

function toSessionUser(me: {
  id: number;
  session_subject: { email: string; display_name: string };
  primary_account_holder: boolean;
}): SessionUser {
  return {
    id: me.id,
    email: me.session_subject.email,
    displayName: me.session_subject.display_name,
    primaryAccountHolder: me.primary_account_holder,
  };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ status: "loading", user: null });

  const refresh = useCallback(async () => {
    const token = await loadSessionToken();
    if (!token) {
      setState({ status: "signedOut", user: null });
      return;
    }
    const { data, response } = await clearPathClient().GET("/v1/me", {});
    if (response.ok && data) {
      setState({ status: "signedIn", user: toSessionUser(data) });
    } else {
      // Token rejected (e.g. MFA not completed, or expired). Stay signed out;
      // the client middleware already cleared a 401 token.
      await clearSessionToken();
      setState({ status: "signedOut", user: null });
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const signIn = useCallback(async (email: string, password: string, staySignedIn: boolean) => {
    const { data, error, response } = await clearPathClient().POST("/v1/auth/login", {
      body: { email, password, stay_signed_in: staySignedIn },
    });
    if (!response.ok || !data) {
      throw new Error(apiErrorMessage(error, "We could not sign you in. Please check your details and try again."));
    }
    await saveSessionToken(data.access_token);
    // Only a fully MFA-verified token grants resource access; the caller routes
    // on next_step (mfa_verify / mfa_setup / select_plan / onboarding / dashboard).
    if (data.mfa_verified) {
      await refresh();
    }
    return { nextStep: data.next_step as NextStep };
  }, [refresh]);

  const signOut = useCallback(async () => {
    try {
      await clearPathClient().DELETE("/v1/auth/session", { body: {} });
    } catch {
      // Best-effort server logout; the local token is what matters on mobile.
    }
    await clearSessionToken();
    setState({ status: "signedOut", user: null });
  }, []);

  const value = useMemo<AuthContextValue>(() => ({ ...state, signIn, signOut, refresh }), [state, signIn, signOut, refresh]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within an AuthProvider.");
  return context;
}
