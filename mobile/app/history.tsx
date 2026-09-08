import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Pressable, RefreshControl, Text, View } from "react-native";
import { useFocusEffect, useRouter } from "expo-router";

import { listJobs } from "../src/api";
import { useAuth } from "../src/auth";
import { AppHeader, LoadingState, ScoreTrendChart, Screen } from "../src/components";
import { FullLink, ProfileChip, SectionHeading } from "../src/coach-ui";
import type { ActiveAnalysisJob } from "../src/contracts";
import { colors, fonts, styles } from "../src/theme";

function statusLabel(job: ActiveAnalysisJob) {
  if (job.status === "SUCCESS") return job.skeletonVideoUrl ? "스켈레톤 재생" : "리포트 보기";
  if (job.status === "FAILED" || job.status === "ERROR") return "분석 실패";
  return "분석 진행 중";
}

export default function HistoryScreen() {
  const router = useRouter();
  const { token, profile } = useAuth();
  const [jobs, setJobs] = useState<ActiveAnalysisJob[]>([]);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<"trend" | "reports">("trend");

  const load = useCallback(async (refresh = false) => {
    if (!token) return;
    refresh ? setRefreshing(true) : setLoading(true);
    setError(null);
    try { setJobs((await listJobs(token)).jobs); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "분석 기록을 불러오지 못했습니다."); }
    finally { setLoading(false); setRefreshing(false); }
  }, [token]);

  useEffect(() => { if (token) void load(); }, [token, load]);
  useFocusEffect(useCallback(() => { if (token) void load(true); return undefined; }, [token, load]));

  const openJob = (job: ActiveAnalysisJob) => {
    if (job.status === "SUCCESS") router.push({ pathname: "/result/[jobId]", params: { jobId: job.jobId } });
    else router.push({ pathname: "/progress/[jobId]", params: { jobId: job.jobId } });
  };
  const completed = useMemo(() => jobs.filter((job) => job.status === "SUCCESS"), [jobs]);
  const latestScore = completed.find((job) => typeof job.postureScore === "number")?.postureScore;

  return (
    <Screen refreshControl={<RefreshControl onRefresh={() => void load(true)} refreshing={refreshing} tintColor={colors.lime} />}>
      <AppHeader title="내 러닝 기록" right={<ProfileChip height={profile?.heightCm ? String(profile.heightCm) : "—"} onPress={() => router.push("/")} />} />
      <View style={{ borderColor: colors.border, borderWidth: 1, flexDirection: "row", marginBottom: 12 }}>
        {(["trend", "reports"] as const).map((item) => <Pressable key={item} onPress={() => setTab(item)} style={{ alignItems: "center", backgroundColor: tab === item ? colors.lime : colors.background, flex: 1, justifyContent: "center", minHeight: 44 }}><Text style={{ color: tab === item ? colors.limeInk : colors.muted, fontSize: 10, fontWeight: "900" }}>{item === "trend" ? "추이" : "분석 리포트"}</Text></Pressable>)}
      </View>
      {loading ? <LoadingState message="기록을 불러오는 중입니다." /> : null}
      {error ? <Pressable onPress={() => void load()} style={{ borderColor: colors.red, borderWidth: 1, marginBottom: 10, minHeight: 48, padding: 10 }}><Text style={{ color: colors.red, fontSize: 11 }}>기록을 불러오지 못했습니다 · 다시 시도</Text></Pressable> : null}

      {!loading && tab === "trend" ? <>
        <View style={{ backgroundColor: colors.surfaceSecondary, borderColor: colors.border, borderWidth: 1, padding: 16 }}><Text style={styles.eyebrow}>최근 {Math.min(completed.length, 4)}회</Text><Text style={{ color: colors.primary, fontSize: 18, fontWeight: "900", lineHeight: 25, marginTop: 8 }}>날짜별 종합 자세 점수를 비교합니다</Text><Text style={[styles.caption, { marginTop: 7 }]}>각 기록에서 분석 리포트와 저장된 스켈레톤을 확인할 수 있습니다.</Text></View>
        <View style={{ backgroundColor: colors.surface, borderColor: colors.border, borderWidth: 1, marginTop: 8, padding: 14 }}><View style={{ alignItems: "flex-end", flexDirection: "row", justifyContent: "space-between" }}><View><Text style={styles.caption}>종합 자세 점수 추이</Text><Text style={{ color: colors.lime, fontFamily: fonts.mono, fontSize: 22, fontWeight: "900", marginTop: 4 }}>{typeof latestScore === "number" ? Math.round(latestScore) : "—"}<Text style={{ color: colors.muted, fontSize: 8 }}>/100</Text></Text></View><Text style={styles.caption}>4개 피처 가중평균</Text></View><ScoreTrendChart jobs={jobs} /></View>
        <View style={{ backgroundColor: colors.surface, borderColor: colors.border, borderWidth: 1, marginTop: 8, padding: 14 }}><SectionHeading label="피처별 추이" meta="최근 4회" /><View style={{ alignItems: "center", borderColor: colors.border, borderTopWidth: 1, justifyContent: "center", marginTop: 12, minHeight: 102 }}><Text style={{ color: colors.primary, fontSize: 12, fontWeight: "800" }}>분석별 피처 점수 추이</Text><Text style={[styles.caption, { marginTop: 6, textAlign: "center" }]}>리포트 데이터가 쌓이면 수직진동·팔꿈치·몸통·전방기울기 추이를 비교합니다.</Text></View></View>
        <FullLink label="과거 분석과 스켈레톤 보기" onPress={() => setTab("reports")} style={{ marginTop: 8 }} />
      </> : null}

      {!loading && tab === "reports" ? <View><SectionHeading label="분석 리포트" meta={`${jobs.length}개`} />{jobs.length ? jobs.map((job) => <Pressable key={job.jobId} onPress={() => openJob(job)} style={({ pressed }) => ({ alignItems: "center", backgroundColor: pressed ? colors.surface : "transparent", borderBottomColor: colors.border, borderBottomWidth: 1, flexDirection: "row", gap: 10, minHeight: 76, paddingHorizontal: 4, paddingVertical: 10 })}><Text style={{ color: colors.lime, fontFamily: fonts.mono, fontSize: 10, fontWeight: "900", width: 48 }}>{new Date(job.createdAt).toLocaleDateString("ko-KR", { month: "2-digit", day: "2-digit" })}</Text><View style={{ flex: 1 }}><Text numberOfLines={1} style={{ color: colors.primary, fontSize: 12, fontWeight: "800" }}>{job.title}</Text><Text style={[styles.caption, { fontSize: 9, marginTop: 5 }]}>{statusLabel(job)}</Text></View>{typeof job.postureScore === "number" ? <Text style={{ borderColor: colors.lime, borderWidth: 1, color: colors.lime, fontFamily: fonts.mono, fontSize: 9, padding: 5 }}>{Math.round(job.postureScore)}점</Text> : null}<Text style={{ color: colors.muted }}>→</Text></Pressable>) : <View style={{ alignItems: "center", borderColor: colors.border, borderWidth: 1, justifyContent: "center", marginTop: 12, minHeight: 130 }}><Text style={{ color: colors.primary, fontSize: 13, fontWeight: "800" }}>아직 분석 기록이 없습니다</Text><Text style={[styles.caption, { marginTop: 6 }]}>첫 러닝 영상을 분석해 보세요.</Text></View>}</View> : null}
    </Screen>
  );
}
