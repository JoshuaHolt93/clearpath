import { Redirect } from "expo-router";
import { ActivityIndicator, StyleSheet, View } from "react-native";

import { useAuth } from "@/lib/auth-context";
import { theme } from "@/lib/theme";

// Entry route: shows a spinner while the stored token is validated, then routes
// to the authenticated home or the login screen. This is the launch gate.
export default function Index() {
  const { status } = useAuth();

  if (status === "loading") {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" color={theme.color.accent} />
      </View>
    );
  }

  return status === "signedIn" ? <Redirect href="/(app)" /> : <Redirect href="/(auth)/login" />;
}

const styles = StyleSheet.create({
  center: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: theme.color.background },
});
