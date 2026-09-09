import type { ActiveAnalysisJob, AnalysisResult, DashboardResponse, FeatureAnalysis, MobileProfile } from "./contracts";

const flowPolls = new Map<string, number>();

export const demoProfile: MobileProfile = {
  userId: "development-fixture", sessionType: "guest", authenticated: false,
  provider: null, email: null, displayName: "개발 fixture", heightCm: 175,
  kakaoLoginEnabled: false,
};

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
    { ...feature("feature1", "키 대비 골반 수직진동", [0.046], 0.028, 0.061, "all_frames"), unit: "ratio", referenceRange: { kind: "reference" as const, min: 0.028, max: 0.061, unit: "ratio", criterionVersion: "demo-v1", evidenceIds: [] }, score: null, visualization: { kind: "range_bar" as const, x_axis: "aggregate_ratio" as const, placement: "summary_metrics" as const } },
    feature("feature2", "팔꿈치 각도", [82, 90, 105, 112], 70, 110.0001, "evaluated_frames"),
    feature("feature3", "몸통 굽힘 각도", values, 10.9, 18.9, "all_frames"),
    feature("feature4", "상체 기울기", partial ? [3, null, null, 5, null, 2] : [2, 3, 4, 5, 2, 3], 1.7, 4.3, "all_frames"),
  ];
  const scored = features.slice(1).map((item) => item.score).filter((score): score is number => typeof score === "number");
  return {
    jobId: id, modelId: "sehyeon-57e4938-demo", modelRelease: "fixture", createdAt: new Date().toISOString(), completedAt: new Date().toISOString(),
    analyzedFrameCount: partial ? 3 : 6, totalFrameCount: 6, features, evidence: [],
    postureScore: scored.length === 3 ? Math.round(scored.reduce((sum, score) => sum + score, 0) / 3) : null,
    runMetrics: { pacePerKm: "4'25\"/km", cadenceSpm: 176, strideLengthM: null, estimationBasis: "development fixture" },
    narrative: llmFailure
      ? { status: "unavailable", model: null, summary: null, priorityActions: [], maintainActions: [], disclaimer: "개발용 LLM 실패 fixture입니다. 의료 진단이나 부상 예측이 아닙니다.", validatorVersion: "service-narrative-2" }
      : { status: "success", model: "fixture", summary: "팔 동작은 대체로 안정적입니다. 몸통과 상체 기울기는 그래프의 기준 구간을 확인해 보세요. 다음 촬영에서도 같은 조건을 유지하세요.", priorityActions: [], maintainActions: [], disclaimer: "개발·시연 전용 데이터이며 의료 진단이나 부상 예측이 아닙니다.", validatorVersion: "service-narrative-2" },
    media: null, runtimeMetadata: { promptVersion: "demo", model: "fixture", validatorVersion: "service-narrative-2", inputTokens: null, outputTokens: null },
  };
}

export function demoJob(id: string): ActiveAnalysisJob | null {
  if (!id.startsWith("demo-")) return null;
  const nextPoll = (flowPolls.get(id) ?? 0) + 1;
  flowPolls.set(id, nextPoll);
  const status = id === "demo-flow"
    ? nextPoll >= 3 ? "SUCCESS" : nextPoll === 2 ? "PROCESSING" : "QUEUED"
    : id === "demo-failed" ? "FAILED" : "PROCESSING";
  return {
    jobId: id, title: "개발 전용 분석 fixture", caseId: id, status,
    stage: status === "SUCCESS" ? "result" : status === "FAILED" ? "keypoints" : status === "QUEUED" ? "queue" : "keypoints",
    progressPct: status === "SUCCESS" ? 100 : null, estimatedCompletionSeconds: null,
    createdAt: new Date(Date.now() - 15_000).toISOString(), startedAt: new Date(Date.now() - 12_000).toISOString(),
    completedAt: status === "SUCCESS" ? new Date().toISOString() : null, updatedAt: new Date().toISOString(),
    heightCm: 175, modelId: "sehyeon-57e4938-demo", modelRelease: "fixture",
    error: status === "FAILED" ? "개발용 최종 실패" : null, postureScore: status === "SUCCESS" ? 75 : null,
  };
}

export function demoDashboard(): DashboardResponse {
  const result = demoResult("demo-normal")!;
  const completedJob: ActiveAnalysisJob = {
    jobId: result.jobId, title: "개발 전용 분석 fixture", caseId: result.jobId,
    status: "SUCCESS", stage: "result", progressPct: 100, estimatedCompletionSeconds: null,
    createdAt: result.createdAt, startedAt: result.createdAt, completedAt: result.completedAt,
    updatedAt: result.completedAt ?? result.createdAt, heightCm: 175,
    modelId: result.modelId, modelRelease: result.modelRelease, error: null,
    postureScore: result.postureScore,
  };
  const latestSignals = result.features.map((item) => ({
    featureId: item.featureId, label: item.label, priority: item.priority,
    verdict: item.verdict, value: item.representativeValue, unit: item.unit,
    referenceRange: item.referenceRange, message: item.interpretation,
    confidencePct: item.confidencePct, confidenceLevel: item.confidenceLevel,
    confidenceAssumed: item.confidenceAssumed, score: item.score,
  }));
  return {
    profile: demoProfile, activeJob: null, jobs: [completedJob], latestSignals,
    prioritySignals: latestSignals.filter((item) => item.verdict === "improve"), trend: null,
  };
}
