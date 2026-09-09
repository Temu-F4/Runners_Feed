import Constants from "expo-constants";

const extra = Constants.expoConfig?.extra as { apiBaseUrl?: string } | undefined;

export const API_BASE_URL = (
  process.env.EXPO_PUBLIC_API_BASE_URL || extra?.apiBaseUrl || ""
).replace(/\/$/, "");

export const NATIVE_REDIRECT_URI = "runnersfeed://auth/callback";
export const DEMO_MODE = process.env.EXPO_PUBLIC_DEMO_FIXTURES === "true";
export const DEMO_FIXTURES_ENABLED = __DEV__ || DEMO_MODE;

if (!API_BASE_URL) {
  console.warn("EXPO_PUBLIC_API_BASE_URL is not configured");
}
