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
  Screen,
  TextField,
} from "../src/components";
import { useAuth } from "../src/auth";
import type { DashboardResponse, ActiveAnalysisJob } from "../src/contracts";
import { colors, spacing, styles } from "../src/theme";

function jobPath(job: ActiveAnalysisJob) {
  return job.status === "SUCCESS"
    ? { pathname: "/result/[jobId]" as const, params: { jobId: job.jobId } }
    : { pathname: "/progress/[jobId]" as const, params: { jobId: job.jobId } };
}

export default function DashboardScreen() {
  const router = useRouter();
  const { token, profile, refreshProfile, signInWithKakao } = useAuth();
  const [dashboard, setDashboard] = useState<DashboardResponse | null>(null);
  const [height, setHeight] = useState(profile?.heightCm ? String(profile.heightCm) : "");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [saving, setSaving] = useState(false);
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
      await refreshProfile();
      await load(true);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "프로필을 저장하지 못했습니다.");
    } finally {
      setSaving(false);
    }
  };

  const login = async () => {
    setLoginError(null);
    try {
      await signInWithKakao();
      await load(true);
    } catch (cause) {
      setLoginError(cause instanceof Error ? cause.message : "Kakao 로그인을 완료하지 못했습니다.");
    }
  };

  return (
    <Screen refreshControl={<RefreshControl onRefresh={() => void load(true)} refreshing={refreshing} tintColor={colors.lime} />}>
      <AppHeader title="오늘의 러닝" right={<Text style={styles.eyebrow}>{profile?.sessionType === "account" ? "ACCOUNT" : "GUEST"}</Text>} />
      {profile?.sessionType === "guest" ? (
        <Panel style={{ borderColor: colors.lime, gap: spacing.md, marginBottom: spacing.lg }}>
          <Text style={{ color: colors.primary, fontSize: 17, fontWeight: "700" }}>기록을 안전하게 이어가세요</Text>
          <Text style={styles.body}>비회원으로도 분석할 수 있습니다. Kakao 로그인 후 다른 기기에서도 기록을 이어갈 수 있습니다.</Text>
          <Button label="Kakao 로그인" onPress={() => void login()} loading={false} />
          {loginError ? <Text style={{ color: colors.red, fontSize: 12 }}>{loginError}</Text> : null}
        </Panel>
      ) : null}
      {loading && !dashboard ? <LoadingState message="최근 분석을 불러오는 중입니다." /> : null}
      {error && !dashboard ? <ErrorState message={error} onRetry={() => void load()} /> : null}
      {dashboard ? (
        <>
          {dashboard.activeJob ? (
            <Panel style={{ gap: spacing.md, marginBottom: spacing.lg }}>
              <Text style={styles.eyebrow}>ACTIVE ANALYSIS</Text>
              <JobCard job={dashboard.activeJob} onPress={() => router.push(jobPath(dashboard.activeJob!))} />
            </Panel>
          ) : null}
          <Panel style={{ gap: spacing.md, marginBottom: spacing.lg }}>
            <Text style={styles.eyebrow}>RUNNER PROFILE</Text>
            <Text style={{ color: colors.primary, fontSize: 18, fontWeight: "700" }}>분석 대상 키</Text>
            <Text style={styles.body}>키는 영상 분석의 정규화 기준으로 사용됩니다. 영상마다 다른 사람을 분석할 때는 분석 시작 화면에서 따로 바꿀 수 있습니다.</Text>
            <TextField keyboardType="decimal-pad" label="키 (cm)" onChangeText={setHeight} value={height} placeholder="예: 175" />
            <Button label="프로필 저장" onPress={() => void saveHeight()} loading={saving} />
          </Panel>
          <View style={{ gap: spacing.md, marginBottom: spacing.lg }}>
            <Text style={styles.eyebrow}>PRIORITY SIGNALS</Text>
            {dashboard.prioritySignals.length ? dashboard.prioritySignals.map((signal, index) => (
              <Panel key={`${index}-${String(signal.featureId ?? "signal")}`}>
                <Text style={{ color: colors.primary, fontWeight: "700" }}>{String(signal.label ?? signal.featureId ?? `신호 ${index + 1}`)}</Text>
                <Text style={[styles.caption, { marginTop: spacing.sm }]}>{String(signal.message ?? "검증된 분석 결과가 준비되면 우선순위를 표시합니다.")}</Text>
              </Panel>
            )) : <EmptyState title="아직 우선 신호가 없습니다" message="검증된 분석 결과가 쌓이면 개선 우선순위를 이곳에 표시합니다." />}
          </View>
          <View style={{ gap: spacing.md }}>
            <Text style={styles.eyebrow}>RECENT ANALYSIS</Text>
            {dashboard.jobs.length ? dashboard.jobs.slice(0, 3).map((job) => <JobCard key={job.jobId} job={job} onPress={() => router.push(jobPath(job))} />) : <EmptyState title="첫 분석을 시작해 보세요" message="러닝 영상을 업로드하면 자세 추적과 지표 계산을 시작합니다." />}
          </View>
          <Button label="새 분석 시작" onPress={() => router.push("/upload")} style={{ marginTop: spacing.xl }} />
          {error ? <Text style={{ color: colors.red, fontSize: 12, marginTop: spacing.md }}>{error}</Text> : null}
        </>
      ) : null}
    </Screen>
  );
}
