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
import { deleteStoredToken, getStoredToken, setStoredToken } from "./token-storage";

WebBrowser.maybeCompleteAuthSession();

const TOKEN_KEY = "runners-feed.mobile.access-token";

interface AuthContextValue {
  ready: boolean;
  error: string | null;
  token: string | null;
  profile: MobileProfile | null;
  signInWithKakao: () => Promise<void>;
  completeKakaoLogin: (code: string) => Promise<void>;
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
  const kakaoExchangePromises = React.useRef(new Map<string, Promise<void>>());

  const saveToken = async (nextToken: string) => {
    await setStoredToken(TOKEN_KEY, nextToken);
    setToken(nextToken);
  };

  const bootstrap = async () => {
    setError(null);
    try {
      const stored = await getStoredToken(TOKEN_KEY);
      if (stored) {
        try {
          const nextProfile = await getMe(stored);
          setToken(stored);
          setProfile(nextProfile);
          return;
        } catch {
          await deleteStoredToken(TOKEN_KEY);
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

  const completeKakaoLogin = async (code: string) => {
    const existing = kakaoExchangePromises.current.get(code);
    if (existing) return existing;

    const pending = (async () => {
      const account = await exchangeKakaoCode(code);
      await saveToken(account.accessToken);
      setProfile(await getMe(account.accessToken));
    })();
    kakaoExchangePromises.current.set(code, pending);
    try {
      await pending;
    } catch (cause) {
      if (kakaoExchangePromises.current.get(code) === pending) {
        kakaoExchangePromises.current.delete(code);
      }
      throw cause;
    }
    setTimeout(() => {
      if (kakaoExchangePromises.current.get(code) === pending) {
        kakaoExchangePromises.current.delete(code);
      }
    }, 60_000);
  };

  const signInWithKakao = async () => {
    if (!token) return;
    const { authorizationUrl } = await startKakaoLogin(token);
    let redirectUrl: string | null = null;
    const subscription = Linking.addEventListener("url", ({ url }) => {
      if (!url.startsWith(NATIVE_REDIRECT_URI)) return;
      redirectUrl = url;
      void WebBrowser.dismissBrowser().catch(() => undefined);
    });

    try {
      const result = await WebBrowser.openAuthSessionAsync(
        authorizationUrl,
        NATIVE_REDIRECT_URI,
      );
      const callbackUrl =
        redirectUrl || (result.type === "success" ? result.url : null);
      if (!callbackUrl) return;
      const parsed = Linking.parse(callbackUrl);
      const code = typeof parsed.queryParams?.code === "string"
        ? parsed.queryParams.code
        : null;
      if (!code) throw new Error("Kakao login did not return an exchange code");
      await completeKakaoLogin(code);
    } finally {
      subscription.remove();
    }
  };

  const signOut = async () => {
    if (token) await apiLogout(token).catch(() => undefined);
    await deleteStoredToken(TOKEN_KEY);
    const guest = await createGuestSession();
    await saveToken(guest.accessToken);
    setProfile(await getMe(guest.accessToken));
  };

  const value = useMemo(
    () => ({ ready, error, token, profile, signInWithKakao, completeKakaoLogin, signOut, refreshProfile, retry: bootstrap }),
    [ready, error, token, profile],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}
