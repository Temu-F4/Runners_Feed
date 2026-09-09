import React, { useEffect, useMemo, useState } from "react";
import { Pressable, Text, View } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useVideoPlayer, VideoView } from "expo-video";

import { createResultVideoUrl, getResult } from "../../src/api";
import { useAuth } from "../../src/auth";
import { AppHeader, Button, FeatureFrameChart, LoadingState, Screen } from "../../src/components";
import { FullLink, ProfileChip, SectionHeading } from "../../src/coach-ui";
import type { AnalysisResult, CoachingAction, FeatureAnalysis } from "../../src/contracts";
import { featureScore, featureScoreLabel, overallScore } from "../../src/scoring";
import { colors, fonts, formatDate, formatValue, spacing, styles } from "../../src/theme";

function StoredResultVideo({ uri, skeleton = false }: { uri: string; skeleton?: boolean }) {
  const player = useVideoPlayer(uri, (instance) => { instance.loop = true; });
  return <View style={{ borderColor: colors.border, borderWidth: 1, marginTop: 8 }}><VideoView contentFit="contain" fullscreenOptions={{ enable: true }} nativeControls player={player} style={{ aspectRatio: 16 / 9, backgroundColor: colors.background, width: "100%" }} /><Text style={{ borderTopColor: colors.border, borderTopWidth: 1, color: colors.muted, fontSize: 9, lineHeight: 14, minHeight: 44, padding: 9 }}>{skeleton ? "저장된 skeleton.mp4 · 리포트와 함께 장기 보관" : "분석 시 생성·저장된 rendered.mp4 · 약 24시간 후 삭제"}</Text></View>;
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
  return "검토 중";
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
  const [limitsOpen, setLimitsOpen] = useState(false);

  useEffect(() => {
    if (!token || !jobId) return;
    getResult(token, jobId).then((value) => { setResult(value); setSelectedId(value.features[0]?.featureId ?? null); }).catch((cause) => setError(cause instanceof Error ? cause.message : "결과를 불러오지 못했습니다.")).finally(() => setLoading(false));
  }, [token, jobId]);

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

  return (
    <Screen>
      <AppHeader title="이번 러닝 분석 결과" right={<ProfileChip height={profile?.heightCm ? String(profile.heightCm) : "—"} onPress={() => router.push("/")} />} />
      {loading ? <LoadingState message="검증된 결과를 불러오는 중입니다." /> : null}
      {error ? <Pressable onPress={() => router.replace({ pathname: "/result/[jobId]", params: { jobId } })} style={{ borderColor: colors.red, borderWidth: 1, marginBottom: 10, minHeight: 48, padding: 10 }}><Text style={{ color: colors.red, fontSize: 11 }}>{error} · 다시 시도</Text></Pressable> : null}
      {result ? <>
        <View style={{ backgroundColor: colors.surfaceSecondary, borderColor: colors.border, borderWidth: 1, padding: 14 }}>
          <SectionHeading label="종합 자세 점수" meta={formatDate(result.completedAt)} />
          <View style={{ alignItems: "flex-end", flexDirection: "row", justifyContent: "space-between", marginTop: 8 }}><View style={{ flex: 1, paddingRight: 10 }}><Text style={styles.caption}>팔꿈치·몸통·상체 기울기 3개 자세 피처의 평균입니다.</Text></View><Text style={{ color: colors.lime, fontFamily: fonts.mono, fontSize: 31, fontWeight: "900" }}>{overallScore(result) ?? "—"}<Text style={{ color: colors.muted, fontSize: 9 }}>/100</Text></Text></View>
          <View style={{ marginTop: 9 }}>{result.features.map((feature) => { const score = featureScore(feature); return <Pressable key={feature.featureId} onPress={() => setSelectedId(feature.featureId)} style={{ alignItems: "center", borderTopColor: colors.border, borderTopWidth: 1, flexDirection: "row", gap: 8, minHeight: 44 }}><Text style={{ color: colors.muted, fontSize: 9, width: 65 }}>{shortLabel(feature)}</Text><View style={{ backgroundColor: colors.border, flex: 1, height: 4 }}><View style={{ backgroundColor: colors.lime, height: 4, width: `${score ?? 0}%` }} /></View><Text style={{ color: colors.primary, fontFamily: fonts.mono, fontSize: 10, fontWeight: "800", width: 26 }}>{score ?? "—"}</Text></Pressable>; })}</View>
        </View>

        {result.runMetrics ? <View style={{ borderColor: colors.border, borderWidth: 1, marginTop: 8 }}><View style={{ flexDirection: "row" }}>{[{ label: "예상 페이스", value: result.runMetrics.pacePerKm ?? "—" }, { label: "케이던스", value: result.runMetrics.cadenceSpm === null ? "—" : `${result.runMetrics.cadenceSpm} spm` }, { label: "보폭", value: result.runMetrics.strideLengthM === null ? "—" : `${result.runMetrics.strideLengthM.toFixed(2)} m` }].map((metric, index) => <View key={metric.label} style={{ borderRightColor: colors.border, borderRightWidth: index < 2 ? 1 : 0, flex: 1, padding: 9 }}><Text style={{ color: colors.muted, fontSize: 8 }}>{metric.label}</Text><Text style={{ color: colors.lime, fontFamily: fonts.mono, fontSize: 11, fontWeight: "800", marginTop: 5 }}>{metric.value}</Text></View>)}</View><Text style={{ borderTopColor: colors.border, borderTopWidth: 1, color: colors.muted, fontSize: 8, padding: 7, textAlign: "center" }}>{result.runMetrics.estimationBasis ?? "1보폭 측정값으로 1분 기준 근사"}</Text></View> : null}

        <View style={{ backgroundColor: colors.surfaceSecondary, borderColor: colors.border, borderTopColor: colors.lime, borderTopWidth: 2, borderWidth: 1, marginTop: 14, padding: 14 }}><SectionHeading label="핵심 피드백" meta={formatDate(result.completedAt)} /><Text style={{ color: colors.primary, fontSize: 17, fontWeight: "900", lineHeight: 23, marginVertical: 10 }}>{result.narrative.summary || "몸통과 팔의 움직임을 먼저 조정해 보세요."}</Text>{actions.length ? actions.map((action, index) => <ActionRow action={action} index={index} key={`${action.featureId}-${index}`} />) : <Text style={styles.caption}>검증된 피드백이 준비되면 이곳에 표시됩니다.</Text>}</View>

        {storedMediaUrl ? <StoredResultVideo uri={storedMediaUrl} skeleton={showingSkeleton} /> : <Button label="저장된 결과 영상 보기" onPress={() => void openVideo()} loading={videoLoading} kind="secondary" style={{ marginTop: 8 }} />}

        {selected ? <View style={{ backgroundColor: colors.surface, borderColor: colors.border, borderWidth: 1, marginTop: 12, padding: 13 }}>
          <SectionHeading label="1보폭 프레임별 자세" meta={`F01–F${String(result.analyzedFrameCount || result.totalFrameCount || selected.series.length).padStart(2, "0")}`} />
          <View style={{ borderColor: colors.border, borderWidth: 1, flexDirection: "row", marginTop: 10 }}>{result.features.map((feature, index) => { const active = feature.featureId === selected.featureId; return <Pressable key={feature.featureId} onPress={() => setSelectedId(feature.featureId)} style={{ alignItems: "center", backgroundColor: active ? colors.lime : colors.background, borderRightColor: colors.border, borderRightWidth: index < result.features.length - 1 ? 1 : 0, flex: 1, justifyContent: "center", minHeight: 44 }}><Text numberOfLines={1} style={{ color: active ? colors.limeInk : colors.muted, fontSize: 9, fontWeight: "800" }}>{shortLabel(feature)}</Text></Pressable>; })}</View>
          <View style={{ alignItems: "flex-end", flexDirection: "row", justifyContent: "space-between", marginTop: 12 }}><View><Text style={{ color: colors.primary, fontSize: 14, fontWeight: "800" }}>{selected.label}</Text><Text style={{ color: selected.verdict === "improve" ? colors.amber : selected.verdict === "maintain" ? colors.lime : colors.muted, fontSize: 10, marginTop: 5 }}>{verdictLabel(selected)}</Text></View><View style={{ alignItems: "flex-end" }}><Text style={{ color: colors.lime, fontFamily: fonts.mono, fontSize: 22, fontWeight: "900" }}>{featureScore(selected) ?? "—"}<Text style={{ color: colors.muted, fontSize: 8 }}>/100</Text></Text><Text style={styles.caption}>{featureScoreLabel(selected)}</Text></View></View>
          <View style={{ borderBottomColor: colors.border, borderBottomWidth: 1, borderTopColor: colors.border, borderTopWidth: 1, flexDirection: "row", justifyContent: "space-between", marginTop: 10, paddingVertical: 9 }}><Text style={styles.caption}>측정 범위 <Text style={{ color: colors.primary, fontFamily: fonts.mono }}>{formatValue(selected.representativeValue, selected.unit)}</Text></Text><Text style={styles.caption}>{selected.referenceRange ? `${formatValue(selected.referenceRange.min, selected.referenceRange.unit)}–${formatValue(selected.referenceRange.max, selected.referenceRange.unit)}` : "기준 준비 중"}</Text></View>
          <FeatureFrameChart feature={selected} />
          <Pressable onPress={() => setLimitsOpen((open) => !open)} style={{ alignItems: "center", borderTopColor: colors.border, borderTopWidth: 1, flexDirection: "row", justifyContent: "space-between", minHeight: 44 }}><Text style={styles.caption}>분석 신뢰도와 한계</Text><Text style={{ color: colors.primary, fontSize: 9, fontWeight: "800" }}>{selected.confidencePct === null ? "—" : `${selected.confidencePct.toFixed(0)}%`} {limitsOpen ? "↑" : "→"}</Text></Pressable>
          {limitsOpen ? <Text style={[styles.caption, { paddingBottom: 8 }]}>{selected.limitation || result.narrative.disclaimer}</Text> : null}
        </View> : null}

        <FullLink label="전체 기록과 과거 스켈레톤 보기" onPress={() => router.push("/history")} style={{ marginTop: 8 }} />
        {result.runtimeMetadata ? <View style={{ borderColor: colors.border, borderWidth: 1, marginTop: 8, padding: 11 }}><Text style={styles.caption}>리포트 생성 정보</Text><Text style={[styles.caption, { fontFamily: fonts.mono, fontSize: 8, marginTop: 7 }]}>prompt {result.runtimeMetadata.promptVersion ?? "—"} · model {result.runtimeMetadata.model ?? result.narrative.model ?? "—"}{`\n`}validator {result.runtimeMetadata.validatorVersion ?? result.narrative.validatorVersion} · tokens {result.runtimeMetadata.inputTokens ?? "—"}/{result.runtimeMetadata.outputTokens ?? "—"}</Text></View> : null}
      </> : null}
    </Screen>
  );
}
