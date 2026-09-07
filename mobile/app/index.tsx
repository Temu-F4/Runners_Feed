import React, { useCallback, useEffect, useState } from "react";
import { RefreshControl, Text, View } from "react-native";
import { useFocusEffect, useRouter } from "expo-router";

import { getDashboard, updateProfile } from "../src/api";
import {
  AppHeader,
  Button,
  EmptyState,
  ErrorState,
  JobCard,
  LoadingState,
  Panel,
  PostureSignalRow,
  PrioritySignals,
  Screen,
  TextField,
  TrendChart,
} from "../src/components";
import { useAuth } from "../src/auth";
import type { ActiveAnalysisJob, DashboardResponse } from "../src/contracts";
import { colors, spacing, styles } from "../src/theme";

function jobPath(job: ActiveAnalysisJob) {
  return job.status === "SUCCESS"
    ? { pathname: "/result/[jobId]" as const, params: { jobId: job.jobId } }
    : { pathname: "/progress/[jobId]" as const, params: { jobId: job.jobId } };
}

export default function DashboardScreen() {
  const router = useRouter();
  const { token, profile, signInWithKakao, signOut } = useAuth();
  const [dashboard, setDashboard] = useState<DashboardResponse | null>(null);
  const [height, setHeight] = useState(profile?.heightCm ? String(profile.heightCm) : "");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [loggingIn, setLoggingIn] = useState(false);
  const [loggingOut, setLoggingOut] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loginError, setLoginError] = useState<string | null>(null);

  const load = useCallback(async (isRefresh = false) => {
    if (!token) return;
    if (isRefresh) setRefreshing(true);
    else setLoading(true);
    setError(null);
    try {
      const response = await getDashboard(token);
      setDashboard(response);
      setHeight(response.profile.heightCm ? String(response.profile.heightCm) : "");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "대시보드를 불러오지 못했습니다.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [token]);

  useEffect(() => {
    if (token) void load();
  }, [token, load]);

  useFocusEffect(useCallback(() => {
    if (token) void load(true);
    return undefined;
  }, [token, load]));

  const saveHeight = async () => {
    if (!token) return;
    const numericHeight = Number(height);
    if (!Number.isFinite(numericHeight) || numericHeight < 50 || numericHeight > 250) {
      setError("키는 50~250cm 범위로 입력해 주세요.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await updateProfile(token, numericHeight);
      const response = await getDashboard(token);
      setDashboard(response);
      setHeight(response.profile.heightCm ? String(response.profile.heightCm) : "");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "프로필을 저장하지 못했습니다.");
    } finally {
      setSaving(false);
    }
  };

  const login = async () => {
    setLoggingIn(true);
    setLoginError(null);
    try {
      await signInWithKakao();
    } catch (cause) {
      setLoginError(cause instanceof Error ? cause.message : "Kakao 로그인을 완료하지 못했습니다.");
    } finally {
      setLoggingIn(false);
    }
  };

  const logout = async () => {
    setLoggingOut(true);
    setError(null);
    try {
      await signOut();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "로그아웃하지 못했습니다.");
    } finally {
      setLoggingOut(false);
    }
  };

  return (
    <Screen refreshControl={<RefreshControl onRefresh={() => void load(true)} refreshing={refreshing} tintColor={colors.lime} />}>
      <AppHeader title="오늘의 러닝" right={<Text style={styles.eyebrow}>{profile?.sessionType === "account" ? "ACCOUNT" : "GUEST"}</Text>} />

      {profile?.sessionType === "guest" ? (
        <Panel style={{ borderColor: colors.lime, gap: spacing.md, marginBottom: spacing.lg }}>
          <Text style={{ color: colors.primary, fontSize: 17, fontWeight: "700" }}>기록을 안전하게 이어가세요</Text>
          <Text style={styles.body}>비회원으로도 분석할 수 있습니다. Kakao 로그인 후 다른 기기에서도 기록을 이어갈 수 있습니다.</Text>
          {profile.kakaoLoginEnabled ? <Button label="Kakao 로그인" loading={loggingIn} onPress={() => void login()} /> : <Text style={styles.caption}>Kakao 로그인이 아직 설정되지 않았습니다.</Text>}
          {loginError ? <Text style={{ color: colors.red, fontSize: 12 }}>{loginError}</Text> : null}
        </Panel>
      ) : (
        <Panel style={{ gap: spacing.md, marginBottom: spacing.lg }}>
          <Text style={styles.eyebrow}>SIGNED-IN RUNNER</Text>
          <Text style={{ color: colors.primary, fontSize: 17, fontWeight: "700" }}>{profile?.displayName || "Kakao 계정"}</Text>
          {profile?.email ? <Text style={styles.caption}>{profile.email}</Text> : null}
          <Button label="로그아웃" kind="secondary" loading={loggingOut} onPress={() => void logout()} />
        </Panel>
      )}

      <Panel style={{ gap: spacing.md, marginBottom: spacing.lg }}>
        <View style={{ alignItems: "center", flexDirection: "row", justifyContent: "space-between" }}>
          <View style={{ flex: 1, gap: spacing.xs }}>
            <Text style={styles.eyebrow}>RUNNER PROFILE</Text>
            <Text style={{ color: colors.primary, fontSize: 18, fontWeight: "700" }}>내 프로필 키</Text>
          </View>
          <Text style={{ color: colors.lime, fontFamily: styles.mono.fontFamily, fontSize: 16 }}>{height ? `${height} cm` : "미입력"}</Text>
        </View>
        <Text style={styles.body}>키는 영상 분석의 정규화 기준으로 사용됩니다.</Text>
        <TextField keyboardType="decimal-pad" label="키 변경 (cm)" onChangeText={setHeight} value={height} placeholder="예: 175" />
        <Button label="프로필 저장" onPress={() => void saveHeight()} loading={saving} />
      </Panel>

      {dashboard?.activeJob ? (
        <View style={{ gap: spacing.sm, marginBottom: spacing.lg }}>
          <Text style={styles.eyebrow}>ACTIVE ANALYSIS</Text>
          <JobCard job={dashboard.activeJob} onPress={() => router.push(jobPath(dashboard.activeJob!))} />
          <Button label="새 분석" onPress={() => router.push("/upload")} />
        </View>
      ) : (
        <Button label="＋  새 분석" onPress={() => router.push("/upload")} style={{ marginBottom: spacing.lg }} />
      )}

      {loading && !dashboard ? <LoadingState message="최근 분석을 불러오는 중입니다." /> : null}
      {error && !dashboard ? <ErrorState message={error} onRetry={() => void load()} /> : null}

      {dashboard ? (
        <>
          {dashboard.trend ? (
            <Panel style={{ gap: spacing.md, marginBottom: spacing.lg }}>
              <View style={{ alignItems: "center", flexDirection: "row", justifyContent: "space-between" }}>
                <View style={{ gap: spacing.xs }}>
                  <Text style={styles.eyebrow}>FORM TREND</Text>
                  <Text style={{ color: colors.primary, fontSize: 17, fontWeight: "700" }}>{dashboard.trend.label}</Text>
                </View>
                <Text style={styles.caption}>최근 기록</Text>
              </View>
              <TrendChart trend={dashboard.trend} />
            </Panel>
          ) : null}

          <PrioritySignals signals={dashboard.prioritySignals} />

          <Panel style={{ gap: spacing.md, marginBottom: spacing.lg }}>
            <View style={{ alignItems: "center", flexDirection: "row", justifyContent: "space-between" }}>
              <View style={{ gap: spacing.xs }}>
                <Text style={styles.eyebrow}>LATEST POSTURE SIGNALS</Text>
                <Text style={{ color: colors.primary, fontSize: 17, fontWeight: "700" }}>내 값과 좋은 범위</Text>
              </View>
              <Text style={styles.caption}>{dashboard.latestSignals.length ? `${dashboard.latestSignals.length}개` : "데이터 없음"}</Text>
            </View>
            {dashboard.latestSignals.length ? dashboard.latestSignals.map((signal) => <PostureSignalRow key={signal.featureId} signal={signal} />) : <Text style={styles.caption}>검증된 결과가 쌓이면 최근 자세 신호가 표시됩니다.</Text>}
          </Panel>

          <View style={{ gap: spacing.md, marginBottom: spacing.lg }}>
            <View style={{ alignItems: "center", flexDirection: "row", justifyContent: "space-between" }}>
              <Text style={styles.eyebrow}>RECENT ANALYSIS</Text>
              <Text style={styles.caption}>{dashboard.jobs.length}건</Text>
            </View>
            {dashboard.jobs.length ? dashboard.jobs.slice(0, 3).map((job) => <JobCard key={job.jobId} job={job} onPress={() => router.push(jobPath(job))} />) : <EmptyState title="첫 분석을 시작해 보세요" message="러닝 영상을 업로드하면 자세 추적과 지표 계산을 시작합니다." />}
          </View>
          {error ? <Text style={{ color: colors.red, fontSize: 12, marginTop: spacing.md }}>{error}</Text> : null}
        </>
      ) : null}
    </Screen>
  );
}
