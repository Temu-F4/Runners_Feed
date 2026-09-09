import type { AnalysisResult, FeatureAnalysis } from "./contracts";

export function featureScore(feature: FeatureAnalysis): number | null {
  if (typeof feature.score === "number" && Number.isFinite(feature.score)) {
    return Math.max(0, Math.min(100, Math.round(feature.score)));
  }
  // The backend owns the denominator policy. Recomputing here would silently
  // turn feature3/4 into evaluated-frame scores when they require all frames.
  return null;
}

export function featureScoreLabel(feature: FeatureAnalysis): string {
  if (typeof feature.goodFrameCount !== "number") return feature.scoreMethod || feature.aggregation || "집계값";
  const denominator = feature.denominatorPolicy === "evaluated_frames"
    ? feature.evaluatedFrameCount
    : feature.sourceFrameCount;
  if (typeof denominator !== "number") return feature.scoreMethod || feature.aggregation || "집계값";
  const label = feature.denominatorPolicy === "evaluated_frames" ? "측정 가능" : "영상 전체";
  return `좋은 구간 ${feature.goodFrameCount} / ${label} ${denominator} 프레임`;
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
