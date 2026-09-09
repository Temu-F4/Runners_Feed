# RunPod HPE handoff: sehyeon-e2fe43e

## Boundary

RunPod performs only video download, HPE inference, primary-runner tracking, five-frame keypoint interpolation, skeleton rendering, H.264 encoding, and artifact upload. OCI performs all four feature calculations, optional narrative generation, report adaptation, skeleton adaptation, persistence, and user-visible state changes.

The RunPod HTTP Proxy is used only while its Pod is running. OCI does not hold a long-lived proxy request open: it submits work and polls with short requests. There is no local OCI inference fallback.

## Asynchronous HTTP contract

`POST /v4/storage-video-analysis` authenticates the shared Bearer token, validates the request identity/hashes, and returns HTTP 202 within seconds:

```json
{"status":"accepted","job_id":"...","attempt_id":"...","remote_job_id":"..."}
```

The same `attempt_id` is the idempotency key. Repeating a submit must return the same logical remote job and must not execute inference twice. OCI persists `remote_job_id` on the `RUNNING` attempt and never submits again once that value exists.

`GET /v4/storage-video-analysis/{remote_job_id}` returns `queued` or `running`; `complete` adds `manifest_object`; `failed` adds `error_code` and `error_message`. Every response repeats the matching `job_id` and `attempt_id`. The manifest path is exactly `jobs/{job_id}/video-analysis/{attempt_id}/pose_manifest.json`.

OCI schedules each poll as a separate Celery task; it neither polls in FastAPI nor sleeps in a worker. `RUNPOD_POLL_INTERVAL_SECONDS` defaults to 10 and `RUNPOD_MAX_POLL_SECONDS` defaults to 4200. Temporary transport/5xx/429 errors are retried, while timeout, 404, malformed responses, and explicit remote failure end the attempt and job consistently.

This repository contains the OCI client and the complete request/manifest contract, but not the RunPod HTTP server deployment. The RunPod owner must implement and deploy that endpoint from the exact plugin release below before production activation.

## Installed model release

- Source: J-sehyeon/Oracle_Project
- Commit: e2fe43e9bb0ee13bd445d8a6d4db240dba84eacc
- Plugin: coach/model_plugins/sehyeon-e2fe43e
- HPE entrypoint: scripts/hpe/hpe.py
- HPE support source: scripts/hpe/utils.py
- Runtime weights: mounted outside Git and verified using model_manifest.json

RunPod must execute the two HPE source files from this exact plugin release. The request source_sha256 and model_sha256 maps are part of the immutable execution identity.

## Transfer contract

OCI sends a video-analysis-request-2.0 payload containing job/attempt identity, immutable input metadata, release hashes, one signed input URL, and signed upload URLs. The worker uploads:

- pose_predictions.json
- details.json
- rendered.mp4 encoded as H.264/yuv420p with the source dimensions and frame count
- pose_manifest.json, uploaded last

Every object name must remain below jobs/{job_id}/video-analysis/{attempt_id}. The completed video-analysis-manifest-2.0 repeats the request identity and hashes, records each artifact SHA-256, byte size, and content type, and includes CUDA provider/GPU evidence plus download, analysis, encode, upload, and total timings.

The same attempt_id may be submitted again only when OCI was interrupted before it persisted the submit response. RunPod must treat this as an idempotent replay and return the existing `remote_job_id`. It must never redirect uploads to a new prefix. OCI persists `GPU_SUCCESS` before queueing postprocess, reuses that attempt after redelivery, and atomically claims `POSTPROCESSING` so only one worker may consume a result.

## OCI continuation

After validating the manifest and downloaded artifacts, OCI runs the source feature extractor and preserves its feature_results.json. The normalizer creates feature_results.service.json; the report and skeleton adapters consume service data while retaining the model raw result separately.

Frame scoring stores source, evaluated, and good frame counts plus evaluation coverage. The current `FEATURE_SCORE_DENOMINATOR=all_frames` policy calculates `good/source * 100`; model-owner approval can switch the single policy setting to `evaluated_frames`. Feature1 is measurement-only and excluded from posture scoring. The overall score is the arithmetic mean of feature2, feature3, and feature4 when available.

Initial confidence is an explicit assumption: `confidence_level=high`, `confidence_pct=null`, and `confidence_assumed=true`. It means the valid measurement is treated as usable, not that posture quality is high; posture quality remains represented by score and verdict.

## Release evidence still required

Quality approval stays pending_modeler_approval until a real CUDA RunPod processes the agreed golden videos and OCI completes feature extraction, report generation, artifact upload, API result retrieval, and a deliberate redelivery of the same attempt. The retained golden package must include `pose_manifest.json`; deployment rechecks its CUDA provider, source and weight identity, and every artifact checksum.
