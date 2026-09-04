# Streamlined Coach GPU A/B

This package compares the same integrated `video_analysis` stage on OCI CPU
and RunPod GPU. Feature extraction, report generation, upload, and cleanup stay
on OCI for both cases.

- CPU case: `video_analysis_cpu_ab`
- GPU case: `video_analysis_gpu_ab`
- RunPod endpoint: `POST /v3/video-analysis`
- GPU failures never fall back to CPU.

The RunPod host must contain the same `coach/` source and model files as OCI.
Start the API with environment variables `COACH_CODE_ROOT`,
`COACH_MODEL_ROOT`, and `RUNPOD_SHARED_TOKEN`, for example:

```sh
uvicorn coach_video_analysis_api:app --host 0.0.0.0 --port 8000
```

Enable only in the A/B worker using `GPU_AB_ENABLED=1`, an HTTPS
`RUNPOD_GPU_BASE_URL`, and `RUNPOD_SHARED_TOKEN_FILE`.

On OCI, add `compose.coach.gpu-ab.yaml` only to the A/B deployment. Ordinary
deployments continue to use `compose.yaml` and `compose.coach.yaml` without the
override.
