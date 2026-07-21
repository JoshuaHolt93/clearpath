import { Link, useRouter } from "expo-router";
import { useState } from "react";
import { ActivityIndicator, KeyboardAvoidingView, Platform, Pressable, StyleSheet, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { useAuth } from "@/lib/auth-context";
import { theme } from "@/lib/theme";

// Login screen — the first real screen, proving the full auth stack end to end:
// form -> POST /v1/auth/login -> store JWT in the secure enclave -> route on the
// API's next_step. MFA / onboarding / plan-selection screens are follow-up
// slices (see MOBILE.md screen roadmap); for now non-dashboard next steps show
// a placeholder so the routing contract is visible.
export default function LoginScreen() {
  const { signIn } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [staySignedIn, setStaySignedIn] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [pendingStep, setPendingStep] = useState<string | null>(null);

  const submit = async () => {
    setBusy(true);
    setError("");
    setPendingStep(null);
    try {
      const { nextStep } = await signIn(email.trim(), password, staySignedIn);
      if (nextStep === "dashboard") {
        router.replace("/(app)");
      } else {
        // e.g. mfa_verify / mfa_setup / select_plan / onboarding — screens TBD.
        setPendingStep(nextStep);
      }
    } catch (signInError) {
      setError(signInError instanceof Error ? signInError.message : "We could not sign you in.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <SafeAreaView style={styles.safe}>
      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={styles.flex}>
        <View style={styles.container}>
          <Text style={styles.brand}>ClearPath Finance</Text>
          <Text style={styles.title}>Sign in</Text>
          <Text style={styles.subtitle}>Budget today. See what&apos;s coming next.</Text>

          {error ? <Text style={styles.error}>{error}</Text> : null}
          {pendingStep ? (
            <Text style={styles.notice}>Signed in. Next step &quot;{pendingStep}&quot; is not built yet on mobile.</Text>
          ) : null}

          <Text style={styles.label}>Email</Text>
          <TextInput
            style={styles.input}
            value={email}
            onChangeText={setEmail}
            autoCapitalize="none"
            autoComplete="email"
            keyboardType="email-address"
            editable={!busy}
            placeholder="you@example.com"
          />

          <Text style={styles.label}>Password</Text>
          <TextInput
            style={styles.input}
            value={password}
            onChangeText={setPassword}
            secureTextEntry
            autoComplete="password"
            editable={!busy}
            placeholder="Your password"
          />

          <Pressable style={styles.checkboxRow} onPress={() => setStaySignedIn((value) => !value)} disabled={busy}>
            <View style={[styles.checkbox, staySignedIn && styles.checkboxOn]} />
            <Text style={styles.checkboxLabel}>Stay signed in on this device</Text>
          </Pressable>

          <Pressable style={[styles.button, busy && styles.buttonDisabled]} onPress={() => void submit()} disabled={busy}>
            {busy ? <ActivityIndicator color={theme.color.accentText} /> : <Text style={styles.buttonText}>Sign In</Text>}
          </Pressable>

          <Link href="/(auth)/login" style={styles.footerLink}>
            Forgot password? (coming soon)
          </Link>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: theme.color.background },
  flex: { flex: 1 },
  container: { flex: 1, padding: theme.spacing(3), gap: theme.spacing(1), justifyContent: "center" },
  brand: { color: theme.color.accent, fontWeight: "700", fontSize: 15 },
  title: { fontSize: 30, fontWeight: "700", color: theme.color.text },
  subtitle: { color: theme.color.textMuted, marginBottom: theme.spacing(2) },
  label: { fontSize: 13, color: theme.color.textSecondary, marginTop: theme.spacing(1) },
  input: {
    borderWidth: 1,
    borderColor: theme.color.border,
    borderRadius: theme.radius.sm,
    padding: theme.spacing(1.5),
    backgroundColor: theme.color.surface,
    color: theme.color.text,
  },
  checkboxRow: { flexDirection: "row", alignItems: "center", gap: theme.spacing(1), marginTop: theme.spacing(1.5) },
  checkbox: { width: 20, height: 20, borderRadius: 5, borderWidth: 1, borderColor: theme.color.border, backgroundColor: theme.color.surface },
  checkboxOn: { backgroundColor: theme.color.accent, borderColor: theme.color.accent },
  checkboxLabel: { color: theme.color.textSecondary },
  button: {
    marginTop: theme.spacing(2.5),
    backgroundColor: theme.color.accent,
    borderRadius: theme.radius.sm,
    padding: theme.spacing(1.75),
    alignItems: "center",
  },
  buttonDisabled: { opacity: 0.6 },
  buttonText: { color: theme.color.accentText, fontWeight: "700", fontSize: 16 },
  footerLink: { color: theme.color.accent, marginTop: theme.spacing(2), textAlign: "center" },
  error: { color: theme.color.danger },
  notice: { color: theme.color.success },
});
