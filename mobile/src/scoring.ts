import type { AnalysisResult, FeatureAnalysis } from "./contracts";

export function featureScore(feature: FeatureAnalysis): number | null {
  if (typeof feature.score === "number" && Number.isFinite(feature.score)) {
    return Math.max(0, Math.min(100, Math.round(feature.score)));
  }
  const range = feature.referenceRange;
  if (!range || range.max <= range.min) return null;
  const measured = feature.series.filter(
    (point) => point.value !== null && Number.isFinite(point.value),
  );
  if (!measured.length) return null;
  const passing = measured.filter(
    (point) => point.value! >= range.min && point.value! <= range.max,
  ).length;
  return Math.round((passing / measured.length) * 100);
}

export function featureScoreLabel(feature: FeatureAnalysis): string {
  if (feature.scoreMethod) return feature.scoreMethod;
  const score = featureScore(feature);
  if (score === null || !feature.referenceRange) return feature.aggregation || "집계값";
  const measured = feature.series.filter(
    (point) => point.value !== null && Number.isFinite(point.value),
  );
  const passing = measured.filter(
    (point) => point.value! >= feature.referenceRange!.min && point.value! <= feature.referenceRange!.max,
  ).length;
  return `좋은 구간 ${passing} / 전체 ${measured.length} 프레임`;
}

export function overallScore(result: AnalysisResult): number | null {
  if (typeof result.postureScore === "number" && Number.isFinite(result.postureScore)) {
    return Math.max(0, Math.min(100, Math.round(result.postureScore)));
  }
  const scores = result.features
    .filter((feature) => feature.featureId !== "feature1")
    .map(featureScore)
    .filter((score): score is number => score !== null);
  if (!scores.length) return null;
  return Math.round(scores.reduce((sum, score) => sum + score, 0) / scores.length);
}
