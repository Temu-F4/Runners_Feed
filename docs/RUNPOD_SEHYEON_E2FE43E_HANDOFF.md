# RunPod HPE handoff: sehyeon-e2fe43e

## Boundary

RunPod performs only video download, HPE inference, primary-runner tracking, five-frame keypoint interpolation, skeleton rendering, H.264 encoding, and artifact upload. OCI performs all four feature calculations, optional narrative generation, report adaptation, skeleton adaptation, persistence, and user-visible state changes.

The RunPod endpoint is a synchronous POST /v4/storage-video-analysis. It must authenticate the shared Bearer token and reject requests whose schema, model ID, source hashes, or weight hashes do not match the installed release. There is no serverless polling contract and no local OCI inference fallback.

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

The same attempt_id may be submitted again after an OCI worker interruption. RunPod must treat this as an idempotent replay: return the already validated manifest or safely replace objects under the same attempt prefix. It must never redirect uploads to a new prefix. OCI persists `GPU_SUCCESS` before queueing postprocess, reuses that attempt after redelivery, and atomically claims `POSTPROCESSING` so only one worker may consume a result.

## OCI continuation

After validating the manifest and downloaded artifacts, OCI runs the source feature extractor and preserves its feature_results.json. The normalizer creates feature_results.service.json; the report and skeleton adapters consume service data while retaining the model raw result separately.

## Release evidence still required

Quality approval stays pending_modeler_approval until a real CUDA RunPod processes the agreed golden videos and OCI completes feature extraction, report generation, artifact upload, API result retrieval, and a deliberate redelivery of the same attempt. The retained golden package must include `pose_manifest.json`; deployment rechecks its CUDA provider, source and weight identity, and every artifact checksum.
