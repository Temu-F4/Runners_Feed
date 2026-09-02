from __future__ import annotations

import time
from contextlib import contextmanager
from collections.abc import Iterator

from job_repository import (
    initialize_job_stages,
    mark_job_stage_finished,
    mark_job_stage_running,
    mark_pending_job_stages_skipped,
)


JOB_STAGE_DEFINITIONS = (
    (1, "input_download"),
    (2, "frame_extract"),
    (3, "pose_inference"),
    (4, "report_generate"),
    (5, "frame_render"),
    (6, "video_compose"),
    (7, "video_encode"),
    (8, "result_upload"),
    (9, "workspace_cleanup"),
)

JOB_STAGE_KEYS = {
    stage_key
    for _, stage_key in JOB_STAGE_DEFINITIONS
}


class JobStageRecorder:
    def __init__(self, job_id: str) -> None:
        self.job_id = job_id
        self.initialized = False

    def initialize(self) -> None:
        initialize_job_stages(
            self.job_id,
            JOB_STAGE_DEFINITIONS,
        )
        self.initialized = True

    @contextmanager
    def track(
        self,
        stage_key: str,
        *,
        failure_status: str = "FAILED",
    ) -> Iterator[None]:
        if not self.initialized:
            raise RuntimeError("Job stages have not been initialized")
        if stage_key not in JOB_STAGE_KEYS:
            raise ValueError(f"Unknown job stage: {stage_key}")
        if failure_status not in {"FAILED", "WARNING"}:
            raise ValueError(
                f"Invalid failure stage status: {failure_status}"
            )

        mark_job_stage_running(self.job_id, stage_key)
        started = time.perf_counter()

        try:
            yield
        except Exception as error:
            mark_job_stage_finished(
                self.job_id,
                stage_key,
                status=failure_status,
                duration_seconds=time.perf_counter() - started,
                error_code=type(error).__name__,
            )
            raise
        else:
            mark_job_stage_finished(
                self.job_id,
                stage_key,
                status="SUCCESS",
                duration_seconds=time.perf_counter() - started,
            )

    def skip_pending(self) -> None:
        if self.initialized:
            mark_pending_job_stages_skipped(self.job_id)
