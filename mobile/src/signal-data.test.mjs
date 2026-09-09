import assert from "node:assert/strict";
import test from "node:test";

import { displaySignals, scoreCohortJobs, signalScore } from "./signal-data.ts";
import { demoDashboard, demoJob, demoResult } from "./demo-results.ts";
import { pollingIsFinal, progressPhaseIndex } from "./progress-data.ts";

const base = (featureId, value, unit, score = null) => ({
  featureId, label: featureId, priority: null, verdict: "maintain",
  value, unit, referenceRange: null, message: "", confidencePct: null,
  confidenceLevel: "high", confidenceAssumed: true, score,
});

test("API feature1 through feature4 map to the four home slots", () => {
  const result = displaySignals([
    base("feature1", 0.046, "ratio"),
    base("feature2", 90, "degree", 0),
    base("feature3", 14, "degree", 75),
    base("feature4", 3, "degree", 100),
  ]);
  assert.deepEqual(result.map((item) => item.displayId), ["feature1", "feature2", "feature3", "feature4"]);
  assert.deepEqual(result.map((item) => item.value), [0.046, 90, 14, 3]);
  assert.equal(result[0].unit, "ratio");
  assert.equal(signalScore(result[0]), null);
  assert.equal(signalScore(result[1]), 0);
  assert.equal(signalScore(result[2]), 75);
  assert.equal(result[1].confidencePct, null);
});

test("missing values remain missing instead of becoming zero", () => {
  const result = displaySignals([]);
  assert.equal(result[0].value, null);
  assert.equal(result[1].score, null);
  assert.equal(signalScore(result[1]), null);
});

test("home fixture uses the same measurement, unit, and server score as detail", () => {
  const detail = demoResult("demo-normal");
  const home = demoDashboard();
  for (const feature of detail.features) {
    const signal = home.latestSignals.find((item) => item.featureId === feature.featureId);
    assert.equal(signal.value, feature.representativeValue);
    assert.equal(signal.unit, feature.unit);
    assert.equal(signal.score, feature.score);
    assert.equal(signal.confidencePct, feature.confidencePct);
  }
});

test("score history stays within the latest model and scoring release", () => {
  const job = (jobId, modelRelease) => ({ jobId, status: "SUCCESS", postureScore: 80, modelId: "model", modelRelease });
  assert.deepEqual(scoreCohortJobs([job("new", "v2"), job("old", "v1")]).map((item) => item.jobId), ["new"]);
});

test("development flow exposes queued, running, and complete server states", () => {
  assert.equal(demoJob("demo-flow").status, "QUEUED");
  assert.equal(demoJob("demo-flow").status, "PROCESSING");
  assert.equal(demoJob("demo-flow").status, "SUCCESS");
  assert.equal(demoResult("demo-flow").narrative.status, "success");
  assert.equal(demoResult("demo-llm-failure").narrative.status, "unavailable");
});

test("server stages map to five user phases and only final states stop polling", () => {
  assert.equal(progressPhaseIndex.queue, 1);
  assert.equal(progressPhaseIndex.keypoints, 2);
  assert.equal(progressPhaseIndex.features, 3);
  assert.equal(progressPhaseIndex.validation, 3);
  assert.equal(progressPhaseIndex.result, 4);
  assert.equal(pollingIsFinal("PROCESSING"), false);
  assert.equal(pollingIsFinal("FAILED"), true);
  assert.equal(pollingIsFinal("SUCCESS"), true);
});
