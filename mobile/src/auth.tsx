import * as SecureStore from "expo-secure-store";
import * as WebBrowser from "expo-web-browser";
import * as Linking from "expo-linking";
import React, { createContext, useContext, useEffect, useMemo, useState } from "react";

import {
  createGuestSession,
  exchangeKakaoCode,
  getMe,
  logout as apiLogout,
  startKakaoLogin,
} from "./api";
import type { MobileProfile } from "./contracts";
import { NATIVE_REDIRECT_URI } from "./config";

WebBrowser.maybeCompleteAuthSession();

const TOKEN_KEY = "runners-feed.mobile.access-token";

interface AuthContextValue {
  ready: boolean;
  error: string | null;
  token: string | null;
  profile: MobileProfile | null;
  signInWithKakao: () => Promise<void>;
  signOut: () => Promise<void>;
  refreshProfile: () => Promise<void>;
  retry: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [profile, setProfile] = useState<MobileProfile | null>(null);

  const saveToken = async (nextToken: string) => {
    await SecureStore.setItemAsync(TOKEN_KEY, nextToken);
    setToken(nextToken);
  };

  const bootstrap = async () => {
    setError(null);
    try {
      const stored = await SecureStore.getItemAsync(TOKEN_KEY);
      if (stored) {
        try {
          const nextProfile = await getMe(stored);
          setToken(stored);
          setProfile(nextProfile);
          return;
        } catch {
          await SecureStore.deleteItemAsync(TOKEN_KEY);
        }
      }
      const guest = await createGuestSession();
      await saveToken(guest.accessToken);
      setProfile(await getMe(guest.accessToken));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "API에 연결할 수 없습니다.");
    }
  };

  useEffect(() => {
    bootstrap().finally(() => setReady(true));
  }, []);

  const refreshProfile = async () => {
    if (token) setProfile(await getMe(token));
  };

  const signInWithKakao = async () => {
    if (!token) return;
    const { authorizationUrl } = await startKakaoLogin(token);
    const result = await WebBrowser.openAuthSessionAsync(
      authorizationUrl,
      NATIVE_REDIRECT_URI,
    );
    if (result.type !== "success") return;
    const parsed = Linking.parse(result.url);
    const code = typeof parsed.queryParams?.code === "string"
      ? parsed.queryParams.code
      : null;
    if (!code) throw new Error("Kakao login did not return an exchange code");
    const account = await exchangeKakaoCode(code);
    await saveToken(account.accessToken);
    setProfile(await getMe(account.accessToken));
  };

  const signOut = async () => {
    if (token) await apiLogout(token).catch(() => undefined);
    await SecureStore.deleteItemAsync(TOKEN_KEY);
    const guest = await createGuestSession();
    await saveToken(guest.accessToken);
    setProfile(await getMe(guest.accessToken));
  };

  const value = useMemo(
    () => ({ ready, error, token, profile, signInWithKakao, signOut, refreshProfile, retry: bootstrap }),
    [ready, error, token, profile],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}
