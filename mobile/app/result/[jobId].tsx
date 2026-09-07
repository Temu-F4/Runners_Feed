import React, { useEffect, useMemo, useState } from "react";
import { Image, Modal, Pressable, Text, useWindowDimensions, View } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import * as Linking from "expo-linking";

import { createResultVideoUrl, getResult } from "../../src/api";
import { useAuth } from "../../src/auth";
import { AppHeader, Button, EmptyState, ErrorState, FeatureCard, LoadingState, Panel, Screen } from "../../src/components";
import type { AnalysisResult, CoachingAction, EvidenceItem, FeatureAnalysis } from "../../src/contracts";
import { colors, formatDate, formatValue, spacing, styles } from "../../src/theme";

function ActionRow({ action, index }: { action: CoachingAction; index: number }) {
  return (
    <View style={{ alignItems: "flex-start", flexDirection: "row", gap: spacing.md, minHeight: 54, paddingVertical: spacing.sm }}>
      <Text style={{ color: action.kind === "improve" ? colors.amber : colors.lime, fontFamily: styles.mono.fontFamily, fontSize: 14, fontWeight: "900" }}>{String(index + 1).padStart(2, "0")}</Text>
      <View style={{ flex: 1, gap: spacing.xs }}>
        <Text style={styles.body}>{action.text}</Text>
        {action.measurementReference ? <Text style={styles.caption}>측정값 {formatValue(action.measurementReference.value, action.measurementReference.unit)}{action.measurementReference.referenceMin !== null && action.measurementReference.referenceMax !== null ? ` · 기준 ${formatValue(action.measurementReference.referenceMin, action.measurementReference.unit)} ~ ${formatValue(action.measurementReference.referenceMax, action.measurementReference.unit)}` : ""}</Text> : null}
      </View>
    </View>
  );
}

function EvidenceSourceCard({ source }: { source: EvidenceItem }) {
  const openSource = () => {
    if (source.doi) void Linking.openURL(`https://doi.org/${source.doi}`);
    else if (source.url) void Linking.openURL(source.url);
  };
  return (
    <View style={{ borderColor: colors.border, borderWidth: 1, gap: spacing.xs, padding: spacing.md }}>
      <Text style={{ color: colors.primary, fontWeight: "700" }}>{source.title}</Text>
      <Text style={styles.caption}>{source.authors}{source.year ? ` · ${source.year}` : ""}</Text>
      <Text style={styles.body}>{source.excerptSummary || "출처 요약이 제공되지 않았습니다."}</Text>
      <Text style={styles.caption}>{source.page ? `p.${source.page} ` : ""}{source.section ?? ""} · 기준 {source.criterionVersion ?? "미버전"}</Text>
      {source.caveat ? <Text style={styles.caption}>주의: {source.caveat}</Text> : null}
      {source.doi || source.url ? <Button label={source.doi ? "DOI 열기" : "출처 열기"} kind="secondary" onPress={openSource} /> : null}
    </View>
  );
}

function EvidenceSheet({ feature, result, onClose }: { feature: FeatureAnalysis | null; result: AnalysisResult; onClose: () => void }) {
  const [sourceExpanded, setSourceExpanded] = useState(false);
  const sources = useMemo(() => {
    if (!feature) return [];
    return result.evidence.filter((item) => feature.evidenceIds.includes(item.evidenceId));
  }, [feature, result.evidence]);
  useEffect(() => setSourceExpanded(false), [feature]);
  if (!feature) return null;
  const representative = sources.find((item) => item.uri) ?? sources[0];
  return (
    <Modal animationType="slide" onRequestClose={onClose} transparent visible>
      <View style={{ backgroundColor: "rgba(0,0,0,0.72)", flex: 1, justifyContent: "flex-end" }}>
        <View style={{ backgroundColor: colors.surface, borderColor: colors.border, borderTopLeftRadius: 12, borderTopRightRadius: 12, borderTopWidth: 1, gap: spacing.lg, maxHeight: "88%", padding: spacing.xl }}>
          <View style={{ alignItems: "center", flexDirection: "row", justifyContent: "space-between" }}>
            <Text style={styles.eyebrow}>EVIDENCE · {feature.featureId}</Text>
            <Pressable accessibilityLabel="상세 근거 닫기" accessibilityRole="button" onPress={onClose} style={{ justifyContent: "center", minHeight: 48 }}><Text style={{ color: colors.lime, fontWeight: "800" }}>닫기</Text></Pressable>
          </View>
          <Text style={{ color: colors.primary, fontSize: 22, fontWeight: "800" }}>{feature.label}</Text>
          <View accessible accessibilityLabel="대표 프레임과 관절 오버레이" style={{ alignItems: "center", backgroundColor: colors.surfaceSecondary, height: 175, justifyContent: "center", overflow: "hidden" }}>
            {representative?.uri ? <Image accessibilityLabel={`${feature.label} 대표 프레임`} source={{ uri: representative.uri }} style={{ height: "100%", width: "100%" }} resizeMode="contain" /> : <><Text style={styles.eyebrow}>REPRESENTATIVE FRAME</Text><Text style={[styles.caption, { marginTop: spacing.sm }]}>대표 프레임과 관절 오버레이가 제공되면 표시됩니다.</Text></>}
          </View>
          <View style={{ borderColor: colors.border, borderTopWidth: 1 }}>
            <View style={{ borderBottomColor: colors.border, borderBottomWidth: 1, gap: spacing.xs, paddingVertical: spacing.md }}><Text style={styles.caption}>측정</Text><Text style={{ color: colors.primary, fontFamily: styles.mono.fontFamily, fontSize: 18, fontWeight: "800" }}>{formatValue(feature.representativeValue, feature.unit)}</Text><Text style={styles.caption}>{feature.aggregation || "대표값"}</Text></View>
            <View style={{ borderBottomColor: colors.border, borderBottomWidth: 1, gap: spacing.xs, paddingVertical: spacing.md }}><Text style={styles.caption}>판단 기준</Text><Text style={styles.body}>{feature.referenceRange ? `${formatValue(feature.referenceRange.min, feature.referenceRange.unit)} ~ ${formatValue(feature.referenceRange.max, feature.referenceRange.unit)}` : "현재 비교 가능한 기준 범위가 없습니다."}</Text><Text style={styles.caption}>{feature.referenceRange?.criterionVersion ? `기준 버전 ${feature.referenceRange.criterionVersion}` : "기준 버전 미제공"}</Text></View>
            <View style={{ borderBottomColor: colors.border, borderBottomWidth: 1, gap: spacing.xs, paddingVertical: spacing.md }}><Text style={styles.caption}>해석</Text><Text style={styles.body}>{feature.interpretation || "해석 문장이 아직 제공되지 않았습니다."}</Text></View>
          </View>
          {feature.coachingAction && feature.confidenceLevel !== "low" && feature.confidenceLevel !== "excluded" ? <Panel style={{ borderColor: colors.lime, gap: spacing.sm }}><Text style={styles.eyebrow}>NEXT RUN</Text><Text style={styles.body}>{feature.coachingAction}</Text></Panel> : null}
          <View style={{ gap: spacing.xs }}><Text style={styles.body}>분석 신뢰도: {feature.confidenceLevel === "high" ? "높음" : feature.confidenceLevel === "medium" ? "보통" : "낮음 · 판단 보류"}{feature.confidencePct === null ? "" : ` · ${feature.confidencePct.toFixed(0)}%`}</Text><Text style={styles.caption}>제한사항: {feature.limitation}</Text></View>
          <Pressable accessibilityRole="button" accessibilityState={{ expanded: sourceExpanded }} onPress={() => setSourceExpanded((expanded) => !expanded)} style={{ alignItems: "center", flexDirection: "row", justifyContent: "space-between", minHeight: 48 }}>
            <Text style={{ color: colors.lime, fontSize: 14, fontWeight: "800" }}>판단 기준과 출처 확인</Text><Text style={{ color: colors.lime }}>{sourceExpanded ? "↑" : "→"}</Text>
          </Pressable>
          {sourceExpanded ? (sources.length ? sources.map((source) => <EvidenceSourceCard key={source.evidenceId} source={source} />) : <Text style={styles.caption}>연결된 출처가 아직 제공되지 않았습니다.</Text>) : null}
        </View>
      </View>
    </Modal>
  );
}

export default function ResultScreen() {
  const { jobId: rawJobId } = useLocalSearchParams<{ jobId: string }>();
  const jobId = Array.isArray(rawJobId) ? rawJobId[0] : rawJobId;
  const router = useRouter();
  const { token } = useAuth();
  const { width } = useWindowDimensions();
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [selected, setSelected] = useState<FeatureAnalysis | null>(null);
  const [loading, setLoading] = useState(true);
  const [videoLoading, setVideoLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token || !jobId) return;
    getResult(token, jobId)
      .then(setResult)
      .catch((cause) => setError(cause instanceof Error ? cause.message : "결과를 불러오지 못했습니다."))
      .finally(() => setLoading(false));
  }, [token, jobId]);

  const openVideo = async () => {
    if (!token || !jobId) return;
    setVideoLoading(true);
    try {
      const response = await createResultVideoUrl(token, jobId);
      await Linking.openURL(response.renderedVideoUrl);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "결과 영상을 열지 못했습니다.");
    } finally {
      setVideoLoading(false);
    }
  };

  return (
    <Screen>
      <AppHeader eyebrow="VALIDATED RESULT" title="분석 결과" />
      {loading ? <LoadingState message="검증된 결과를 불러오는 중입니다." /> : null}
      {error ? <ErrorState message={error} onRetry={() => router.replace({ pathname: "/result/[jobId]", params: { jobId } })} /> : null}
      {result ? (
        <>
          <Panel style={{ gap: spacing.md, marginBottom: spacing.lg }}>
            <Text style={styles.eyebrow}>{formatDate(result.completedAt)}</Text>
            <Text style={{ color: colors.primary, fontSize: 20, fontWeight: "800" }}>{result.narrative.summary || "측정 결과를 확인해 보세요"}</Text>
            <Text style={styles.body}>분석 프레임 {result.analyzedFrameCount.toLocaleString()} / 전체 {result.totalFrameCount.toLocaleString()}</Text>
            <Text style={styles.caption}>{result.modelId ?? "모델 ID 미제공"}{result.modelRelease ? ` · ${result.modelRelease}` : ""}</Text>
            <Button label="결과 영상 보기" onPress={() => void openVideo()} loading={videoLoading} kind="secondary" />
          </Panel>

          {result.narrative.priorityActions.length || result.narrative.maintainActions.length ? (
            <Panel style={{ gap: spacing.sm, marginBottom: spacing.lg }}>
              <Text style={styles.eyebrow}>COACHING · VALIDATED</Text>
              {result.narrative.priorityActions.slice(0, 3).map((action, index) => <ActionRow action={action} index={index} key={`${action.featureId}-${index}`} />)}
              {result.narrative.maintainActions.map((action, index) => <ActionRow action={action} index={result.narrative.priorityActions.length + index} key={`${action.featureId}-maintain-${index}`} />)}
            </Panel>
          ) : <Panel style={{ marginBottom: spacing.lg }}><Text style={styles.caption}>검증된 코칭 문장이 준비되면 이곳에 표시됩니다. 현재는 모델이 제공한 측정값만 표시합니다.</Text></Panel>}

          <View style={{ gap: spacing.md }}>
            <View style={{ alignItems: "center", flexDirection: "row", justifyContent: "space-between" }}><Text style={styles.eyebrow}>FRAME-BY-FRAME FEATURES</Text><Text style={styles.caption}>{result.features.length}개</Text></View>
            {result.features.length ? <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.sm }}>{result.features.map((feature) => <View key={feature.featureId} style={{ width: width >= 380 ? "48.5%" : "100%" }}><FeatureCard feature={feature} onDetails={() => setSelected(feature)} /></View>)}</View> : <EmptyState title="표시할 지표가 없습니다" message="모델 결과에 유효한 지표가 없거나 검증에서 제외되었습니다." />}
          </View>
          <Panel style={{ gap: spacing.sm, marginTop: spacing.lg }}>
            <Text style={{ color: colors.primary, fontWeight: "700" }}>분석 신뢰도와 한계</Text>
            <Text style={styles.body}>{result.narrative.disclaimer}</Text>
            <Text style={styles.caption}>이 서비스는 의료 진단이나 부상 예측이 아닙니다.</Text>
          </Panel>
          <Button label="다음 러닝 다시 분석" onPress={() => router.push("/upload")} style={{ marginTop: spacing.lg }} />
          <EvidenceSheet feature={selected} result={result} onClose={() => setSelected(null)} />
        </>
      ) : null}
    </Screen>
  );
}
