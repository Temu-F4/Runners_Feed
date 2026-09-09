# sehyeon-e2fe43e

Model snapshot from `J-sehyeon/Oracle_Project` commit `e2fe43e9bb0ee13bd445d8a6d4db240dba84eacc`.

The model algorithms are preserved. Two integration-only patches are recorded in the manifest: `feature1()` returns the result it already calculates, and the narrative entrypoint uses the service workspace and standard OpenAI environment names. Raw `feature_results.json` and `pose_predictions.json` remain unchanged; service adapters create normalized artifacts separately.

The incomplete, unused `scripts/hpe/pose_track.py`, notebooks, media, generated results, caches, and model binaries are intentionally excluded. Runtime weights are mounted separately and verified with the hashes in the manifest.

Quality status remains `pending_modeler_approval` until the golden videos pass on a real RunPod CUDA worker.
