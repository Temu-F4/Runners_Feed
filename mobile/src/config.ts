import Constants from "expo-constants";

const extra = Constants.expoConfig?.extra as { apiBaseUrl?: string } | undefined;

export const API_BASE_URL = (
  process.env.EXPO_PUBLIC_API_BASE_URL || extra?.apiBaseUrl || ""
).replace(/\/$/, "");

export const NATIVE_REDIRECT_URI = "runnersfeed://auth/callback";

if (!API_BASE_URL) {
  console.warn("EXPO_PUBLIC_API_BASE_URL is not configured");
}
