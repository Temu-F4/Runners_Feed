import React, { useEffect, useRef, useState } from "react";
import { useLocalSearchParams, useRouter } from "expo-router";

import { useAuth } from "../../src/auth";
import { Button, ErrorState, LoadingState, Screen } from "../../src/components";

export default function KakaoCallbackScreen() {
  const params = useLocalSearchParams<{
    code?: string | string[];
    error?: string | string[];
  }>();
  const code = Array.isArray(params.code) ? params.code[0] : params.code;
  const kakaoError = Array.isArray(params.error) ? params.error[0] : params.error;
  const router = useRouter();
  const { completeKakaoLogin } = useAuth();
  const handledCode = useRef<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!code || handledCode.current === code) return;
    handledCode.current = code;
    void completeKakaoLogin(code)
      .then(() => router.replace("/"))
      .catch((cause) => {
        setError(cause instanceof Error ? cause.message : "Kakao 로그인을 완료하지 못했습니다.");
      });
  }, [code, completeKakaoLogin, router]);

  if (kakaoError || (!code && !error)) {
    return (
      <Screen>
        <ErrorState message="Kakao 로그인이 취소되었거나 완료되지 않았습니다." />
        <Button label="대시보드로 돌아가기" onPress={() => router.replace("/")} />
      </Screen>
    );
  }

  if (error) {
    return (
      <Screen>
        <ErrorState message={error} />
        <Button label="대시보드로 돌아가기" onPress={() => router.replace("/")} />
      </Screen>
    );
  }

  return (
    <Screen>
      <LoadingState message="Kakao 로그인을 완료하는 중입니다." />
    </Screen>
  );
}
