# sehyeon-57e4938

Model snapshot from `J-sehyeon/Oracle_Project` commit `57e4938ff93360cd171016b6615b3d3b94bf27e3`.

The model algorithms are preserved. Upstream now includes `feature1()`'s return, direction-aware elbow selection, cadence, and pace. Integration-only safety patches are recorded in the manifest: cadence/pace does not mutate the shared feature scale, validates finite positive measurements, and the elbow window handles empty/single-frame groups while retaining source frame indices. The narrative entrypoint reads the normalized service feature contract so it cannot silently use a different scoring policy. Raw `feature_results.json` and `pose_predictions.json` remain unchanged; service adapters create normalized artifacts separately.

The incomplete, unused `scripts/hpe/pose_track.py`, notebooks, media, generated results, caches, and model binaries are intentionally excluded. Runtime weights are mounted separately and verified with the hashes in the manifest.

Quality status remains `pending_modeler_approval` until the golden videos pass on a real RunPod CUDA worker.
