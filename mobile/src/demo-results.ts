import type { AnalysisResult, FeatureAnalysis } from "./contracts";

const feature = (
  featureId: string,
  label: string,
  values: Array<number | null>,
  min: number,
  max: number,
  denominatorPolicy: "all_frames" | "evaluated_frames",
): FeatureAnalysis => {
  const good = values.filter((value) => value !== null && value >= min && value < max).length;
  const measured = values.filter((value) => value !== null).length;
  const denominator = denominatorPolicy === "evaluated_frames" ? measured : values.length;
  return {
    featureId, label, priority: null, verdict: good === denominator ? "maintain" : "improve",
    representativeValue: measured ? values.filter((value): value is number => value !== null).reduce((sum, value) => sum + value, 0) / measured : null,
    unit: "degree", aggregation: "mean",
    referenceRange: { kind: "recommended", min, max, unit: "degree", criterionVersion: "demo-v1", evidenceIds: [] },
    series: values.map((value, frameIndex) => ({ frameIndex, timestampMs: frameIndex * 33, value, confidencePct: null })),
    interpretation: "개발용 fixture 측정 결과입니다.", coachingAction: "그래프의 기준 구간과 측정값을 함께 확인하세요.",
    confidencePct: null, confidenceLevel: measured ? "high" : "excluded", confidenceAssumed: true,
    limitation: "개발·시연 전용 데이터이며 실제 분석 결과가 아닙니다.", evidenceIds: [],
    score: denominator ? Math.round(good / denominator * 10000) / 100 : null,
    scoreMethod: "reference-band frame compliance", denominatorPolicy,
    goodFrameCount: good, evaluatedFrameCount: measured, sourceFrameCount: values.length,
    evaluationCoveragePct: values.length ? measured / values.length * 100 : null,
    visualization: { kind: "line", x_axis: denominatorPolicy === "evaluated_frames" ? "measurable_frame" : "video_frame", placement: "feature_grid" },
  };
};

export function demoResult(id: string): AnalysisResult | null {
  if (!id.startsWith("demo-")) return null;
  const partial = id === "demo-partial";
  const llmFailure = id === "demo-llm-failure";
  const values = partial ? [12, null, null, 15, null, 20] : [12, 13, 14, 15, 19, 16];
  const features = [
    { ...feature("feature1", "키 대비 골반 수직진동", [0.046], 0.028, 0.061, "all_frames"), unit: "ratio", score: null, visualization: { kind: "range_bar", x_axis: "aggregate_ratio", placement: "summary_metrics" } },
    feature("feature2", "팔꿈치 각도", [82, 90, 105, 112], 70, 110.0001, "evaluated_frames"),
    feature("feature3", "몸통 굽힘 각도", values, 10.9, 18.9, "all_frames"),
    feature("feature4", "상체 기울기", partial ? [3, null, null, 5, null, 2] : [2, 3, 4, 5, 2, 3], 1.7, 4.3, "all_frames"),
  ];
  const scored = features.slice(1).map((item) => item.score).filter((score): score is number => typeof score === "number");
  return {
    jobId: id, modelId: "sehyeon-57e4938-demo", modelRelease: "fixture", createdAt: new Date().toISOString(), completedAt: new Date().toISOString(),
    analyzedFrameCount: partial ? 3 : 6, totalFrameCount: 6, features, evidence: [],
    postureScore: scored.length === 3 ? Math.round(scored.reduce((sum, score) => sum + score, 0) / 3) : null,
    runMetrics: { pacePerKm: "4:25 /km", cadenceSpm: 176, strideLengthM: null, estimationBasis: "development fixture" },
    narrative: llmFailure
      ? { status: "unavailable", model: null, summary: null, priorityActions: [], maintainActions: [], disclaimer: "개발용 LLM 실패 fixture입니다. 의료 진단이나 부상 예측이 아닙니다.", validatorVersion: "service-narrative-2" }
      : { status: "success", model: "fixture", summary: "팔 동작은 대체로 안정적입니다. 몸통과 상체 기울기는 그래프의 기준 구간을 확인해 보세요. 다음 촬영에서도 같은 조건을 유지하세요.", priorityActions: [], maintainActions: [], disclaimer: "개발·시연 전용 데이터이며 의료 진단이나 부상 예측이 아닙니다.", validatorVersion: "service-narrative-2" },
    media: null, runtimeMetadata: { promptVersion: "demo", model: "fixture", validatorVersion: "service-narrative-2", inputTokens: null, outputTokens: null },
  };
}
