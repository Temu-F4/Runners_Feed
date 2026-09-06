from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from maintenance_repository import (
    clear_input_object,
    clear_transient_result_objects,
    delete_user,
    list_expired_failed_jobs,
    list_expired_inputs,
    list_expired_transient_results,
    list_inactive_guest_users,
    list_user_artifacts,
)
from object_storage_gateway import ObjectStorageGateway
from run_cleanup import remove_successful_run


LOGGER = logging.getLogger(__name__)
RUN_ROOT = Path(os.getenv("WORKSPACE_ROOT", "/workspace")) / "run"
TRANSIENT_RESULT_FIELDS = (
    "result_details_object",
    "result_predictions_object",
    "result_video_object",
)
ALL_RESULT_FIELDS = (
    *TRANSIENT_RESULT_FIELDS,
    "result_report_object",
    "result_skeleton_object",
)


def _positive_int(name: str, default: int) -> int:
    value = int(os.getenv(name, str(default)))
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def _delete_user_artifacts(storage: ObjectStorageGateway, user_id) -> None:
    for artifact in list_user_artifacts(user_id):
        input_name = artifact.get("input_object_name")
        if input_name:
            storage.delete_input(input_name)
        for field in ALL_RESULT_FIELDS:
            object_name = artifact.get(field)
            if object_name:
                storage.delete_result(object_name)


def run_once(now: datetime | None = None) -> dict[str, int]:
    current_time = now or datetime.now(timezone.utc)
    batch_size = _positive_int("MAINTENANCE_BATCH_SIZE", 100)
    transient_cutoff = current_time - timedelta(
        hours=_positive_int("TRANSIENT_ARTIFACT_TTL_HOURS", 24)
    )
    failed_cutoff = current_time - timedelta(
        hours=_positive_int("FAILED_RUN_TTL_HOURS", 48)
    )
    guest_cutoff = current_time - timedelta(
        days=_positive_int("INACTIVE_GUEST_TTL_DAYS", 365)
    )
    storage = ObjectStorageGateway()
    counts = {"inputs": 0, "results": 0, "failed_runs": 0, "guest_users": 0}

    for job in list_expired_inputs(transient_cutoff, batch_size):
        storage.delete_input(job["input_object_name"])
        clear_input_object(job["job_id"])
        counts["inputs"] += 1

    for job in list_expired_transient_results(transient_cutoff, batch_size):
        for field in TRANSIENT_RESULT_FIELDS:
            object_name = job.get(field)
            if object_name:
                storage.delete_result(object_name)
        clear_transient_result_objects(job["job_id"])
        counts["results"] += 1

    for job in list_expired_failed_jobs(failed_cutoff, batch_size):
        run_dir = RUN_ROOT / str(job["job_id"])
        if remove_successful_run(run_dir, run_root=RUN_ROOT):
            counts["failed_runs"] += 1

    for user in list_inactive_guest_users(guest_cutoff, batch_size):
        _delete_user_artifacts(storage, user["user_id"])
        delete_user(user["user_id"])
        counts["guest_users"] += 1

    return counts


def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    interval = _positive_int("MAINTENANCE_INTERVAL_SECONDS", 21600)
    while True:
        try:
            LOGGER.info("Maintenance completed: %s", run_once())
        except Exception:
            LOGGER.exception("Maintenance run failed")
        time.sleep(interval)


if __name__ == "__main__":
    main()
