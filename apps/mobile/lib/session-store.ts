import * as SecureStore from "expo-secure-store";
import { Platform } from "react-native";

// The mobile app is stateless on the client-security side: it holds the API's
// JWT access token in the device secure enclave (iOS Keychain / Android
// Keystore) via expo-secure-store, and sends it as a Bearer token on every API
// call. This is the key difference from the web app, which uses Next BFF routes
// forwarding an httpOnly session cookie. There is NO server tier on mobile.
//
// expo-secure-store is unavailable on web (Expo web), so we fall back to an
// in-memory value there — acceptable only for the `expo start --web` dev preview;
// production mobile is iOS/Android where SecureStore is backed by the enclave.

const SESSION_TOKEN_KEY = "clearpath.session.token";

let inMemoryToken: string | null = null;
const useSecureStore = Platform.OS !== "web";

export async function saveSessionToken(token: string): Promise<void> {
  if (useSecureStore) {
    await SecureStore.setItemAsync(SESSION_TOKEN_KEY, token, {
      keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
    });
  } else {
    inMemoryToken = token;
  }
}

export async function loadSessionToken(): Promise<string | null> {
  if (useSecureStore) {
    return SecureStore.getItemAsync(SESSION_TOKEN_KEY);
  }
  return inMemoryToken;
}

export async function clearSessionToken(): Promise<void> {
  if (useSecureStore) {
    await SecureStore.deleteItemAsync(SESSION_TOKEN_KEY);
  } else {
    inMemoryToken = null;
  }
}
