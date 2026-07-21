import { Redirect } from "expo-router";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { useAuth } from "@/lib/auth-context";
import { theme } from "@/lib/theme";

// Authenticated home. For the scaffold this proves the bearer-authenticated data
// path (it renders the signed-in user from /v1/me via the auth context) and the
// sign-out flow. The real Today/dashboard screen — safe-to-spend, accounts,
// budgets, upcoming cash — is the next mobile slice (see MOBILE.md roadmap).
export default function AppHome() {
  const { status, user, signOut } = useAuth();

  if (status === "signedOut") return <Redirect href="/(auth)/login" />;

  return (
    <SafeAreaView style={styles.safe}>
      <ScrollView contentContainerStyle={styles.container}>
        <Text style={styles.brand}>ClearPath Finance</Text>
        <Text style={styles.title}>Welcome{user ? `, ${user.displayName}` : ""}</Text>
        <View style={styles.card}>
          <Text style={styles.cardTitle}>You are signed in</Text>
          <Text style={styles.meta}>Email: {user?.email ?? "—"}</Text>
          <Text style={styles.meta}>Role: {user?.primaryAccountHolder ? "Primary account holder" : "Shared household access"}</Text>
        </View>
        <Text style={styles.note}>
          This is the mobile scaffold home. The Today dashboard, budgets, transactions, and cash projections come in
          follow-up slices — the auth, secure storage, and typed API foundation they build on is in place.
        </Text>
        <Pressable style={styles.signOut} onPress={() => void signOut()}>
          <Text style={styles.signOutText}>Sign Out</Text>
        </Pressable>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: theme.color.background },
  container: { padding: theme.spacing(3), gap: theme.spacing(1.5) },
  brand: { color: theme.color.accent, fontWeight: "700", fontSize: 15 },
  title: { fontSize: 26, fontWeight: "700", color: theme.color.text },
  card: {
    backgroundColor: theme.color.surface,
    borderWidth: 1,
    borderColor: theme.color.border,
    borderRadius: theme.radius.md,
    padding: theme.spacing(2),
    gap: theme.spacing(0.5),
    marginTop: theme.spacing(1),
  },
  cardTitle: { fontWeight: "600", fontSize: 16, color: theme.color.text },
  meta: { color: theme.color.textSecondary },
  note: { color: theme.color.textMuted, marginTop: theme.spacing(1), lineHeight: 20 },
  signOut: {
    marginTop: theme.spacing(2),
    borderWidth: 1,
    borderColor: theme.color.danger,
    borderRadius: theme.radius.sm,
    padding: theme.spacing(1.5),
    alignItems: "center",
  },
  signOutText: { color: theme.color.danger, fontWeight: "600" },
});
