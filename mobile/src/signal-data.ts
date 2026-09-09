import type { ActiveAnalysisJob, PostureSignal } from "./contracts";

export const featureOrder = ["feature1", "feature2", "feature3", "feature4"] as const;

export const featureMeta: Record<string, { label: string; short: string }> = {
  feature1: { label: "골반 수직 진폭", short: "수직진폭" },
  feature2: { label: "팔꿈치 각도", short: "팔꿈치" },
  feature3: { label: "몸통 굽힘", short: "몸통" },
  feature4: { label: "전방 자세 기울기", short: "전방기울기" },
};

export function canonicalFeatureId(value: string) {
  const id = value.toLowerCase();
  if (id === "feature1" || id.includes("vertical")) return "feature1";
  if (id === "feature2" || id.includes("elbow")) return "feature2";
  if (id === "feature3" || id.includes("trunk")) return "feature3";
  if (id === "feature4" || id.includes("lean")) return "feature4";
  return id;
}

export type DisplaySignal = PostureSignal & { displayId: string; short: string };

export function displaySignals(signals: PostureSignal[]): DisplaySignal[] {
  const byId = new Map(signals.map((signal) => [canonicalFeatureId(signal.featureId), signal]));
  return featureOrder.map((displayId) => {
    const found = byId.get(displayId);
    const meta = featureMeta[displayId]!;
    return {
      featureId: found?.featureId ?? displayId,
      displayId,
      label: found?.label || meta.label,
      short: meta.short,
      priority: found?.priority ?? null,
      verdict: found?.verdict ?? "review",
      value: found?.value ?? null,
      unit: found?.unit ?? (displayId === "feature1" ? "ratio" : "degree"),
      referenceRange: found?.referenceRange ?? null,
      message: found?.message ?? "분석 결과가 쌓이면 이곳에 표시됩니다.",
      confidencePct: found?.confidencePct ?? null,
      confidenceLevel: found?.confidenceLevel ?? "excluded",
      confidenceAssumed: found?.confidenceAssumed ?? false,
      score: found?.score ?? null,
    };
  });
}

export function signalScore(signal: PostureSignal): number | null {
  return typeof signal.score === "number" && Number.isFinite(signal.score)
    ? Math.max(0, Math.min(100, Math.round(signal.score)))
    : null;
}

export function scoreCohortJobs(jobs: ActiveAnalysisJob[]): ActiveAnalysisJob[] {
  const scored = jobs.filter((job) => job.status === "SUCCESS" && typeof job.postureScore === "number");
  const latest = scored[0];
  if (!latest) return [];
  return scored.filter((job) => job.modelId === latest.modelId && job.modelRelease === latest.modelRelease);
}
