import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Linking, Pressable, Text, View } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useVideoPlayer, VideoView } from "expo-video";

import { createResultVideoUrl, getResult } from "../../src/api";
import { useAuth } from "../../src/auth";
import { AppHeader, Button, FeatureFrameChart, FeatureMiniChart, LoadingState, Screen } from "../../src/components";
import { FullLink, ProfileChip, SectionHeading } from "../../src/coach-ui";
import type { AnalysisResult, CoachingAction, FeatureAnalysis } from "../../src/contracts";
import { colors, fonts, formatDate, formatValue, styles } from "../../src/theme";

function StoredResultVideo({ uri, skeleton = false }: { uri: string; skeleton?: boolean }) {
  const player = useVideoPlayer(uri, (instance) => { instance.loop = true; });
  return <View style={{ borderColor: colors.border, borderWidth: 1, marginTop: 8 }}><VideoView contentFit="contain" fullscreenOptions={{ enable: true }} nativeControls player={player} style={{ aspectRatio: 16 / 9, backgroundColor: colors.background, width: "100%" }} /><Text style={{ borderTopColor: colors.border, borderTopWidth: 1, color: colors.muted, fontSize: 9, lineHeight: 14, minHeight: 44, padding: 9 }}>{skeleton ? "주요 관절 움직임을 표시한 자세 분석 영상입니다." : "분석된 자세를 영상으로 확인해 보세요."}</Text></View>;
}

function ActionRow({ action, index }: { action: CoachingAction; index: number }) {
  return <View style={{ alignItems: "center", borderTopColor: colors.border, borderTopWidth: 1, flexDirection: "row", gap: 10, minHeight: 42 }}><Text style={{ color: colors.amber, fontFamily: fonts.mono, fontSize: 9, fontWeight: "900", width: 24 }}>{String(index + 1).padStart(2, "0")}</Text><Text style={{ color: colors.primary, flex: 1, fontSize: 11, fontWeight: "700", lineHeight: 16 }}>{action.text}</Text></View>;
}

function featureKey(feature: FeatureAnalysis) {
  const id = feature.featureId.toLowerCase();
  if (id.includes("vertical")) return "vertical";
  if (id.includes("elbow")) return "elbow";
  if (id.includes("trunk")) return "trunk";
  if (id.includes("lean")) return "lean";
  return id;
}

function shortLabel(feature: FeatureAnalysis) {
  const key = featureKey(feature);
  if (key === "vertical") return "수직진동";
  if (key === "elbow") return "팔꿈치";
  if (key === "trunk") return "몸통";
  if (key === "lean") return "전방기울기";
  return feature.label;
}

function verdictLabel(feature: FeatureAnalysis) {
  if (feature.verdict === "maintain") return "좋은 구간";
  if (feature.verdict === "improve") return "조정 필요";
  if (feature.verdict === "excluded") return "분석 제외";
  if (feature.verdict === "unavailable") return "측정 불가";
  return "검토 중";
}

function cardFeedback(feature: FeatureAnalysis) {
  return feature.coachingAction
    || (feature.verdict === "maintain" ? "현재 자세를 유지해 보세요." : "자세를 조금 조정해 보세요.");
}

function RunMetricCell({ label, value }: { label: string; value: string }) {
  return <View style={{ flex: 1, minHeight: 92, padding: 10 }}><Text style={{ color: colors.muted, fontSize: 8 }}>{label}</Text><Text style={{ color: colors.lime, fontFamily: fonts.mono, fontSize: 14, fontWeight: "900", marginTop: 9 }}>{value}</Text></View>;
}

function paceLabel(value: string | null | undefined) {
  if (!value) return "—";
  const match = value.trim().match(/^(\d+)[:'](\d{1,2})(?:\"?\s*\/?\s*km)?$/);
  return match ? `${Number(match[1])}'${String(Number(match[2])).padStart(2, "0")}"/km` : value;
}

function VerticalObservationCell({ feature }: { feature: FeatureAnalysis | null }) {
  const range = feature?.referenceRange ?? null;
  const value = feature?.representativeValue ?? null;
  const inRange = value !== null && range !== null && value >= range.min && value <= range.max;
  const position = value !== null && range
    ? Math.max(0, Math.min(100, ((value - range.min) / (range.max - range.min)) * 100))
    : 50;
  return <View style={{ borderLeftColor: colors.border, borderLeftWidth: 1, flex: 1.45, minHeight: 92, padding: 10 }}>
    <Text style={{ color: colors.muted, fontSize: 8 }}>수직 진폭</Text>
    <Text style={{ color: inRange ? colors.lime : value === null ? colors.muted : colors.amber, fontSize: 8, fontWeight: "800", marginTop: 5 }}>{value === null ? "측정 불가" : inRange ? "관찰 범위 안" : "관찰 범위 밖"}</Text>
    <View style={{ backgroundColor: colors.surfaceRaised, height: 5, marginTop: 9, position: "relative" }}><View style={{ backgroundColor: "rgba(201,255,56,0.28)", height: 5, left: 0, position: "absolute", right: 0 }} />{value !== null && range ? <View style={{ backgroundColor: inRange ? colors.lime : colors.amber, borderRadius: 4, height: 9, left: `${position}%`, marginLeft: -3, marginTop: -2, position: "absolute", width: 6 }} /> : null}</View>
    <View style={{ flexDirection: "row", justifyContent: "space-between", marginTop: 4 }}><Text style={{ color: colors.muted, fontFamily: fonts.mono, fontSize: 6 }}>{range ? range.min.toFixed(3) : "0.028"}</Text><Text style={{ color: colors.primary, fontFamily: fonts.mono, fontSize: 7, fontWeight: "800" }}>{value === null ? "—" : value.toFixed(3)}</Text><Text style={{ color: colors.muted, fontFamily: fonts.mono, fontSize: 6 }}>{range ? range.max.toFixed(3) : "0.061"}</Text></View>
  </View>;
}

export default function ResultScreen() {
  const { jobId: rawJobId } = useLocalSearchParams<{ jobId: string }>();
  const jobId = Array.isArray(rawJobId) ? rawJobId[0] : rawJobId;
  const router = useRouter();
  const { token, profile } = useAuth();
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [videoLoading, setVideoLoading] = useState(false);
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadResult = useCallback(() => {
    if (!jobId || (!token && !jobId.startsWith("demo-"))) return;
    setLoading(true);
    setError(null);
    getResult(token ?? "", jobId).then((value) => { setResult(value); setSelectedId(value.features.find((feature) => feature.featureId === "feature2")?.featureId ?? value.features[0]?.featureId ?? null); }).catch((cause) => setError(cause instanceof Error ? cause.message : "결과를 불러오지 못했습니다.")).finally(() => setLoading(false));
  }, [token, jobId]);

  useEffect(() => { loadResult(); }, [loadResult]);

  const openExerciseVideo = async (url: string) => {
    setError(null);
    try {
      if (!(await Linking.canOpenURL(url))) throw new Error("지원되는 영상 링크가 아닙니다.");
      await Linking.openURL(url);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "추천 영상을 열지 못했습니다.");
    }
  };

  const openVideo = async () => {
    if (!token || !jobId) return;
    setVideoLoading(true);
    try { setVideoUrl((await createResultVideoUrl(token, jobId)).renderedVideoUrl); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "결과 영상을 열지 못했습니다."); }
    finally { setVideoLoading(false); }
  };

  const selected = useMemo(() => result?.features.find((feature) => feature.featureId === selectedId) ?? result?.features[0] ?? null, [result, selectedId]);
  const storedMediaUrl = videoUrl ?? result?.media?.renderedVideoUrl ?? result?.media?.skeletonVideoUrl ?? null;
  const showingSkeleton = !videoUrl && !result?.media?.renderedVideoUrl && Boolean(result?.media?.skeletonVideoUrl);
  const actions = result ? [...result.narrative.priorityActions, ...result.narrative.maintainActions].slice(0, 2) : [];
  const vertical = result?.features.find((feature) => feature.featureId === "feature1") ?? null;
  const postureFeatures = result?.features.filter((feature) => ["feature2", "feature3", "feature4"].includes(feature.featureId)) ?? [];

  return (
    <Screen>
      <AppHeader title="이번 러닝 분석 결과" right={<ProfileChip height={profile?.heightCm ? String(profile.heightCm) : "—"} onPress={() => router.push("/")} />} />
      {loading ? <LoadingState message="검증된 결과를 불러오는 중입니다." /> : null}
      {error ? <Pressable onPress={loadResult} style={{ borderColor: colors.red, borderWidth: 1, marginBottom: 10, minHeight: 48, padding: 10 }}><Text style={{ color: colors.red, fontSize: 11 }}>{error} · 다시 시도</Text></Pressable> : null}
      {result ? <>
        <View style={{ borderColor: colors.border, borderWidth: 1, flexDirection: "row", marginBottom: 8 }}>
          <RunMetricCell label="페이스" value={paceLabel(result.runMetrics?.pacePerKm)} />
          <View style={{ borderLeftColor: colors.border, borderLeftWidth: 1, flex: 1 }}><RunMetricCell label="케이던스" value={result.runMetrics?.cadenceSpm == null ? "—" : `${result.runMetrics.cadenceSpm} spm`} /></View>
          <VerticalObservationCell feature={vertical} />
        </View>
        <View style={{ backgroundColor: colors.surfaceSecondary, borderColor: colors.border, borderWidth: 1, padding: 14 }}>
          <SectionHeading label="자세 지표" meta={formatDate(result.completedAt)} />
          <View style={{ borderColor: colors.border, borderWidth: 1, flexDirection: "row", flexWrap: "wrap", marginTop: 9 }}>{postureFeatures.map((feature) => { const active = feature.featureId === selected?.featureId; return <Pressable accessibilityLabel={`${shortLabel(feature)} 측정값 ${formatValue(feature.representativeValue, feature.unit)}, ${cardFeedback(feature)}, 프레임 그래프 보기`} key={feature.featureId} onPress={() => setSelectedId(feature.featureId)} style={{ backgroundColor: active ? colors.surfaceRaised : colors.background, borderBottomColor: colors.border, borderBottomWidth: 1, borderRightColor: colors.border, borderRightWidth: 1, minHeight: 172, padding: 9, width: "50%" }}><View style={{ alignItems: "center", flexDirection: "row", justifyContent: "space-between" }}><Text style={{ color: active ? colors.lime : colors.muted, fontSize: 8, fontWeight: "800" }}>{shortLabel(feature)}</Text><Text style={{ color: colors.primary, fontFamily: fonts.mono, fontSize: 14, fontWeight: "900" }}>{formatValue(feature.representativeValue, feature.unit)}</Text></View><View style={{ marginTop: 7 }}><FeatureMiniChart feature={feature} /></View><Text numberOfLines={1} style={{ color: colors.primary, fontSize: 8, fontWeight: "700", lineHeight: 12, marginTop: 6 }}>{cardFeedback(feature)}</Text></Pressable>; })}<View accessibilityLabel="향후 feature5 영역" style={{ borderBottomColor: colors.border, borderBottomWidth: 1, borderRightColor: colors.border, borderRightWidth: 1, minHeight: 172, width: "50%" }} /></View>
        </View>

        {storedMediaUrl ? <StoredResultVideo uri={storedMediaUrl} skeleton={showingSkeleton} /> : <Button label="저장된 결과 영상 보기" onPress={() => void openVideo()} loading={videoLoading} kind="secondary" style={{ marginTop: 8 }} />}

        {selected ? <View style={{ backgroundColor: colors.surface, borderColor: colors.border, borderWidth: 1, marginTop: 12, padding: 13 }}>
          <SectionHeading label="영상 전체 프레임별 자세" meta={`F01–F${String(result.totalFrameCount || selected.series.length).padStart(2, "0")}`} />
          <View style={{ borderColor: colors.border, borderWidth: 1, flexDirection: "row", marginTop: 10 }}>{postureFeatures.map((feature, index) => { const active = feature.featureId === selected.featureId; return <Pressable key={feature.featureId} onPress={() => setSelectedId(feature.featureId)} style={{ alignItems: "center", backgroundColor: active ? colors.lime : colors.background, borderRightColor: colors.border, borderRightWidth: index < postureFeatures.length - 1 ? 1 : 0, flex: 1, justifyContent: "center", minHeight: 44 }}><Text numberOfLines={1} style={{ color: active ? colors.limeInk : colors.muted, fontSize: 9, fontWeight: "800" }}>{shortLabel(feature)}</Text></Pressable>; })}</View>
          <View style={{ marginTop: 12 }}><Text style={{ color: colors.primary, fontSize: 14, fontWeight: "800" }}>{selected.label}</Text><Text style={{ color: selected.verdict === "improve" ? colors.amber : selected.verdict === "maintain" ? colors.lime : colors.muted, fontSize: 10, marginTop: 5 }}>{verdictLabel(selected)}</Text></View>
          <View style={{ borderBottomColor: colors.border, borderBottomWidth: 1, borderTopColor: colors.border, borderTopWidth: 1, flexDirection: "row", justifyContent: "space-between", marginTop: 10, paddingVertical: 9 }}><Text style={styles.caption}>측정 범위 <Text style={{ color: colors.primary, fontFamily: fonts.mono }}>{formatValue(selected.representativeValue, selected.unit)}</Text></Text><Text style={styles.caption}>{selected.referenceRange ? `${formatValue(selected.referenceRange.min, selected.referenceRange.unit)}–${formatValue(selected.referenceRange.max, selected.referenceRange.unit)}` : "기준 준비 중"}</Text></View>
          <FeatureFrameChart feature={selected} />
          <View style={{ borderTopColor: colors.border, borderTopWidth: 1, paddingVertical: 9 }}>
            <Text style={[styles.body, { marginTop: 8 }]}>{selected.coachingAction || selected.interpretation || "기본 코칭 문장이 제공되지 않았습니다."}</Text>
          </View>
        </View> : null}

        <View style={{ backgroundColor: colors.surfaceSecondary, borderColor: colors.border, borderTopColor: colors.lime, borderTopWidth: 2, borderWidth: 1, marginTop: 14, padding: 14 }}><SectionHeading label="AI 러닝 코치 종합 리포트" meta={formatDate(result.completedAt)} /><Text style={{ color: colors.primary, fontSize: 17, fontWeight: "900", lineHeight: 23, marginVertical: 10 }}>{result.narrative.summary || "AI 코칭 설명이 준비되지 않았습니다."}</Text>{actions.length ? actions.map((action, index) => <ActionRow action={action} index={index} key={`${action.featureId}-${index}`} />) : <Text style={styles.caption}>측정 결과와 자세 그래프를 확인해 보세요.</Text>}{result.narrative.exerciseVideos?.length ? <View style={{ borderTopColor: colors.border, borderTopWidth: 1, marginTop: 10, paddingTop: 8 }}><Text style={[styles.caption, { marginBottom: 4 }]}>추천 자세 연습 영상</Text>{result.narrative.exerciseVideos.map((video) => <Pressable accessibilityRole="link" key={video.id} onPress={() => void openExerciseVideo(video.url)} style={{ justifyContent: "center", minHeight: 40 }}><Text style={{ color: colors.lime, fontSize: 10, fontWeight: "800" }}>{video.title} →</Text></Pressable>)}</View> : null}<Text style={[styles.caption, { fontSize: 9, marginTop: 10 }]}>{result.narrative.disclaimer}</Text></View>
        <FullLink label="전체 기록과 과거 스켈레톤 보기" onPress={() => router.push("/history")} style={{ marginTop: 8 }} />
      </> : null}
    </Screen>
  );
}
