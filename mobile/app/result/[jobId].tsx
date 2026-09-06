import React, { useEffect, useState } from "react";
import { Modal, Pressable, Text, View } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import * as Linking from "expo-linking";

import { createResultVideoUrl, getResult } from "../../src/api";
import { useAuth } from "../../src/auth";
import { AppHeader, Button, EmptyState, ErrorState, FeatureCard, LoadingState, Panel, Screen } from "../../src/components";
import type { AnalysisResult, FeatureAnalysis } from "../../src/contracts";
import { colors, formatDate, formatValue, spacing, styles } from "../../src/theme";

function narrativeText(action: Record<string, unknown>) {
  return typeof action.text === "string" ? action.text : null;
}

export default function ResultScreen() {
  const { jobId: rawJobId } = useLocalSearchParams<{ jobId: string }>();
  const jobId = Array.isArray(rawJobId) ? rawJobId[0] : rawJobId;
  const router = useRouter();
  const { token } = useAuth();
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
            <Text style={{ color: colors.primary, fontSize: 20, fontWeight: "800" }}>측정 결과를 확인해 보세요</Text>
            <Text style={styles.body}>분석 프레임 {result.analyzedFrameCount.toLocaleString()} / 전체 {result.totalFrameCount.toLocaleString()}</Text>
            <Button label="결과 영상 보기" onPress={() => void openVideo()} loading={videoLoading} kind="secondary" />
          </Panel>
          {result.narrative.status === "success" && result.narrative.priorityActions.length ? (
            <Panel style={{ gap: spacing.md, marginBottom: spacing.lg }}>
              <Text style={styles.eyebrow}>COACHING</Text>
              {result.narrative.priorityActions.map((action, index) => {
                const text = narrativeText(action);
                return text ? <Text key={`${index}-${text}`} style={styles.body}>{index + 1}. {text}</Text> : null;
              })}
            </Panel>
          ) : <Panel style={{ marginBottom: spacing.lg }}><Text style={styles.caption}>현재 모델은 수치 결과를 우선 제공합니다. 검증된 코칭 문장이 준비되면 이곳에 표시됩니다.</Text></Panel>}
          <View style={{ gap: spacing.md }}>
            <Text style={styles.eyebrow}>FEATURES</Text>
            {result.features.length ? result.features.map((feature) => <FeatureCard key={feature.featureId} feature={feature} onDetails={() => setSelected(feature)} />) : <EmptyState title="표시할 지표가 없습니다" message="모델 결과에 유효한 지표가 없거나 검증에서 제외되었습니다." />}
          </View>
          <Panel style={{ gap: spacing.sm, marginTop: spacing.lg }}>
            <Text style={{ color: colors.primary, fontWeight: "700" }}>분석 한계</Text>
            <Text style={styles.body}>{result.narrative.disclaimer}</Text>
            <Text style={styles.caption}>이 서비스는 의료 진단이나 부상 예측이 아닙니다.</Text>
          </Panel>
        </>
      ) : null}
      <Modal animationType="slide" onRequestClose={() => setSelected(null)} transparent visible={selected !== null}>
        <View style={{ backgroundColor: "rgba(0,0,0,0.72)", flex: 1, justifyContent: "flex-end" }}>
          <View style={{ backgroundColor: colors.surface, borderColor: colors.border, borderTopLeftRadius: 8, borderTopRightRadius: 8, borderTopWidth: 1, gap: spacing.lg, padding: spacing.xl }}>
            <View style={{ alignItems: "center", flexDirection: "row", justifyContent: "space-between" }}>
              <Text style={styles.eyebrow}>EVIDENCE</Text>
              <Pressable accessibilityRole="button" onPress={() => setSelected(null)} style={{ minHeight: 48, justifyContent: "center" }}><Text style={{ color: colors.lime, fontWeight: "800" }}>닫기</Text></Pressable>
            </View>
            {selected ? <>
              <Text style={{ color: colors.primary, fontSize: 22, fontWeight: "800" }}>{selected.label}</Text>
              <Text style={{ color: colors.lime, fontFamily: styles.mono.fontFamily, fontSize: 24 }}>{formatValue(selected.representativeValue, selected.unit)}</Text>
              <Text style={styles.body}>{selected.interpretation || "해석 가능한 문장이 아직 제공되지 않았습니다."}</Text>
              {selected.referenceRange ? <Text style={styles.body}>기준 범위: {formatValue(selected.referenceRange.min, selected.referenceRange.unit)} ~ {formatValue(selected.referenceRange.max, selected.referenceRange.unit)}</Text> : <Text style={styles.caption}>비교 기준 범위가 제공되지 않았습니다.</Text>}
              {selected.coachingAction && selected.confidenceLevel !== "low" && selected.confidenceLevel !== "excluded" ? <Text style={styles.body}>다음 행동: {selected.coachingAction}</Text> : null}
              <Text style={styles.caption}>제한사항: {selected.limitation}</Text>
              <Text style={styles.caption}>근거 ID: {selected.evidenceIds.length ? selected.evidenceIds.join(", ") : "없음"}</Text>
            </> : null}
          </View>
        </View>
      </Modal>
    </Screen>
  );
}
