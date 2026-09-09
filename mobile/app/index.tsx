import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Modal, Pressable, RefreshControl, Switch, Text, TextInput, View } from "react-native";
import { useFocusEffect, useRouter } from "expo-router";

import { getDashboard, updateProfile } from "../src/api";
import { useAuth } from "../src/auth";
import { AppHeader, Button, LoadingState, Screen } from "../src/components";
import {
  displaySignals,
  FeatureTabs,
  FullLink,
  ImprovementChips,
  ProfileChip,
  ScoreOverview,
  SectionHeading,
  SignalReading,
  SignalStrip,
} from "../src/coach-ui";
import type { ActiveAnalysisJob, DashboardResponse } from "../src/contracts";
import { colors, fonts, styles } from "../src/theme";

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
  const [selectedFeature, setSelectedFeature] = useState("feature1");
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [accountBusy, setAccountBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [profileOpen, setProfileOpen] = useState(false);
  const [notificationsEnabled, setNotificationsEnabled] = useState(true);

  const load = useCallback(async (refresh = false) => {
    if (!token) return;
    refresh ? setRefreshing(true) : setLoading(true);
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

  useEffect(() => { if (token) void load(); }, [token, load]);
  useFocusEffect(useCallback(() => { if (token) void load(true); return undefined; }, [token, load]));

  const saveHeight = async () => {
    if (!token) return;
    const value = Number(height);
    if (!Number.isFinite(value) || value < 50 || value > 250) {
      setError("키는 50~250cm 범위로 입력해 주세요.");
      return;
    }
    setSaving(true);
    try {
      await updateProfile(token, value);
      await load(true);
      setProfileOpen(false);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "프로필을 저장하지 못했습니다.");
    } finally {
      setSaving(false);
    }
  };

  const accountAction = async () => {
    setAccountBusy(true);
    setError(null);
    try {
      if (profile?.sessionType === "guest") await signInWithKakao();
      else await signOut();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "계정 작업을 완료하지 못했습니다.");
    } finally {
      setAccountBusy(false);
    }
  };

  const signals = useMemo(() => displaySignals(dashboard?.latestSignals ?? []), [dashboard?.latestSignals]);
  const selected = signals.find((signal) => signal.displayId === selectedFeature) ?? signals[0]!;
  const latestJob = dashboard?.jobs.find((job) => job.status === "SUCCESS");
  const activeJob = dashboard?.activeJob;
  const latestDate = latestJob ? new Date(latestJob.createdAt).toLocaleDateString("ko-KR", { month: "2-digit", day: "2-digit" }) : "최근 분석 없음";

  return (
    <Screen refreshControl={<RefreshControl onRefresh={() => void load(true)} refreshing={refreshing} tintColor={colors.lime} />}>
      <AppHeader
        title={"달리는 순간,\n데이터로 읽습니다"}
        right={<View style={{ alignItems: "center", flexDirection: "row", gap: 6 }}>
          {activeJob ? <Pressable onPress={() => router.push(jobPath(activeJob))} style={{ alignItems: "center", borderColor: colors.lime, borderWidth: 1, justifyContent: "center", minHeight: 48, minWidth: 50, paddingHorizontal: 7 }}><Text style={{ color: colors.lime, fontFamily: fonts.mono, fontSize: 10, fontWeight: "900" }}>{activeJob.progressPct === null ? "분석 중" : `${Math.round(activeJob.progressPct)}%`}</Text></Pressable> : null}
          <ProfileChip height={height} onPress={() => setProfileOpen(true)} />
        </View>}
      />

      {loading && !dashboard ? <LoadingState message="최근 분석을 불러오는 중입니다." /> : null}
      <ScoreOverview jobs={dashboard?.jobs ?? []} onPress={() => router.push("/history")} />
      <ImprovementChips signals={dashboard?.latestSignals ?? []} onPress={() => latestJob ? router.push(jobPath(latestJob)) : router.push("/upload")} />

      <View style={{ backgroundColor: colors.surface, borderColor: colors.border, borderWidth: 1, marginTop: 12, padding: 13 }}>
        <SectionHeading label="최근 분석 자세" meta={latestDate} />
        <FeatureTabs items={signals} selected={selectedFeature} onSelect={setSelectedFeature} />
        <SignalReading signal={selected} />
      </View>
      <SignalStrip items={signals} onSelect={setSelectedFeature} />
      <FullLink label={latestJob ? "최근 분석 자세히 보기" : "첫 분석 시작하기"} onPress={() => latestJob ? router.push(jobPath(latestJob)) : router.push("/upload")} style={{ marginTop: 8 }} />

      {error ? <Pressable onPress={() => void load()} style={{ borderColor: colors.red, borderWidth: 1, marginTop: 10, minHeight: 48, padding: 10 }}><Text style={{ color: colors.red, fontSize: 11 }}>데이터를 불러오지 못했습니다 · 다시 시도</Text></Pressable> : null}

      <Modal animationType="slide" onRequestClose={() => setProfileOpen(false)} transparent visible={profileOpen}>
        <Pressable onPress={() => setProfileOpen(false)} style={{ backgroundColor: "rgba(0,0,0,0.68)", flex: 1, justifyContent: "flex-end" }}>
          <Pressable onPress={() => undefined} style={{ backgroundColor: colors.surfaceRaised, borderColor: colors.border, borderTopLeftRadius: 12, borderTopRightRadius: 12, borderWidth: 1, padding: 20 }}>
            <View style={{ alignSelf: "center", backgroundColor: "#596158", borderRadius: 3, height: 4, marginBottom: 14, width: 42 }} />
            <View style={{ alignItems: "flex-start", flexDirection: "row", justifyContent: "space-between" }}><View><Text style={styles.eyebrow}>PROFILE</Text><Text style={{ color: colors.primary, fontSize: 21, fontWeight: "900", marginTop: 5 }}>분석 프로필</Text></View><Pressable onPress={() => setProfileOpen(false)} style={{ justifyContent: "center", minHeight: 44, paddingHorizontal: 8 }}><Text style={{ color: colors.muted, fontSize: 11 }}>닫기</Text></Pressable></View>
            <View style={{ alignItems: "center", borderTopColor: colors.border, borderTopWidth: 1, flexDirection: "row", justifyContent: "space-between", marginTop: 14, minHeight: 70 }}><View><Text style={{ color: colors.primary, fontSize: 12, fontWeight: "800" }}>키</Text><Text style={[styles.caption, { marginTop: 4 }]}>새 분석의 기본값</Text></View><View style={{ alignItems: "center", flexDirection: "row", gap: 5 }}><TextInput keyboardType="decimal-pad" onChangeText={setHeight} value={height} placeholder="175" placeholderTextColor={colors.muted} style={{ backgroundColor: colors.background, borderColor: colors.border, borderWidth: 1, color: colors.lime, fontFamily: fonts.mono, fontSize: 16, fontWeight: "800", height: 44, paddingHorizontal: 10, textAlign: "right", width: 72 }} /><Text style={styles.caption}>cm</Text></View></View>
            <View style={{ alignItems: "center", borderTopColor: colors.border, borderTopWidth: 1, flexDirection: "row", justifyContent: "space-between", minHeight: 70 }}><View><Text style={{ color: colors.primary, fontSize: 12, fontWeight: "800" }}>분석 완료 알림</Text><Text style={[styles.caption, { marginTop: 4 }]}>현재 기기에서 알림</Text></View><Switch onValueChange={setNotificationsEnabled} trackColor={{ false: colors.border, true: colors.lime }} thumbColor={colors.primary} value={notificationsEnabled} /></View>
            <Button label="저장하고 닫기" loading={saving} onPress={() => void saveHeight()} />
            <Button label={profile?.sessionType === "guest" ? "Kakao 로그인" : "로그아웃"} loading={accountBusy} onPress={() => void accountAction()} kind="secondary" style={{ marginTop: 8 }} />
          </Pressable>
        </Pressable>
      </Modal>
    </Screen>
  );
}
