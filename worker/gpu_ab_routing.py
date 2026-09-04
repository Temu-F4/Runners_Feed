"""Opt-in routing for the streamlined video-analysis A/B test."""

from __future__ import annotations

import os
from collections.abc import Mapping


DEFAULT_CPU_CASE_ID = "video_analysis_cpu_ab"
DEFAULT_GPU_CASE_ID = "video_analysis_gpu_ab"


def pipeline_command(
    case_id: str,
    command: list[str],
    *,
    environ: Mapping[str, str] | None = None,
) -> list[str]:
    config = os.environ if environ is None else environ
    cpu_case = config.get("GPU_AB_CPU_CASE_ID", DEFAULT_CPU_CASE_ID)
    gpu_case = config.get("GPU_AB_GPU_CASE_ID", DEFAULT_GPU_CASE_ID)
    if not cpu_case or not gpu_case or cpu_case == gpu_case:
        raise RuntimeError("GPU A/B case IDs must be distinct and non-empty")

    if case_id == gpu_case:
        if config.get("GPU_AB_ENABLED", "0") != "1":
            raise RuntimeError(
                "GPU A/B is disabled; the GPU case will not fall back to CPU"
            )
        backend = "runpod"
    else:
        # The explicit CPU case and every ordinary job remain on OCI CPU.
        backend = "local"

    return [
        "env",
        f"COACH_VIDEO_ANALYSIS_BACKEND={backend}",
        *command,
    ]
