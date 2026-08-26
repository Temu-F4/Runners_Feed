import os
from contextlib import asynccontextmanager
from uuid import uuid4

import oci
import psycopg
from celery import Celery
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from redis import Redis

from app.database import (
    create_job,
    get_job as get_persisted_job,
    initialize_database,
    mark_job_dispatch_failed,
)


celery_client = Celery(
    "runners_feed_api",
    broker=os.getenv(
        "CELERY_BROKER_URL",
        "redis://redis:6379/1",
    ),
    backend=os.getenv(
        "CELERY_RESULT_BACKEND",
        "redis://redis:6379/2",
    ),
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    yield


app = FastAPI(
    title="Runners Feed API",
    lifespan=lifespan,
)


class CreateInferenceJobRequest(BaseModel):
    case_id: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$",
    )
    input_object_name: str = Field(
        min_length=1,
        max_length=1024,
    )

    @field_validator("input_object_name")
    @classmethod
    def require_mp4_object(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized.lower().endswith(".mp4"):
            raise ValueError("input_object_name must reference an MP4")
        return normalized


def _serialize_job(job: dict) -> dict:
    response = {
        "job_id": str(job["job_id"]),
        "case_id": job["case_id"],
        "input_object_name": job["input_object_name"],
        "status": job["status"],
        "created_at": job["created_at"],
        "started_at": job["started_at"],
        "completed_at": job["completed_at"],
        "updated_at": job["updated_at"],
    }

    if job["status"] == "SUCCESS":
        response["result_objects"] = {
            "details": job["result_details_object"],
            "predictions": job["result_predictions_object"],
            "rendered_video": job["result_video_object"],
        }

    if job["status"] == "FAILED":
        response["error"] = job["error_code"] or "inference_failed"

    return response


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/health/dependencies")
def dependency_health():
    checks = {}
    response_status = 200

    try:
        with psycopg.connect(
            os.environ["DATABASE_URL"],
            connect_timeout=5,
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()

        checks["postgres"] = "ok"

    except Exception as error:
        checks["postgres"] = f"error:{type(error).__name__}"
        response_status = 503

    try:
        redis_client = Redis.from_url(
            os.environ["REDIS_URL"],
            socket_connect_timeout=5,
        )

        checks["redis"] = "ok" if redis_client.ping() else "error"

    except Exception as error:
        checks["redis"] = f"error:{type(error).__name__}"
        response_status = 503

    overall_status = "ok" if response_status == 200 else "degraded"

    return JSONResponse(
        status_code=response_status,
        content={
            "status": overall_status,
            "dependencies": checks,
        },
    )


@app.post("/jobs", status_code=202)
def create_inference_job(request: CreateInferenceJobRequest):
    job_id = str(uuid4())

    create_job(
        job_id=job_id,
        case_id=request.case_id,
        input_object_name=request.input_object_name,
    )

    try:
        celery_client.send_task(
            "inference.run_object_storage",
            args=[request.case_id, request.input_object_name],
            task_id=job_id,
            queue="inference",
        )
    except Exception as error:
        mark_job_dispatch_failed(job_id)
        raise HTTPException(
            status_code=503,
            detail="Failed to dispatch inference job",
        ) from error

    job = get_persisted_job(job_id)
    if job is None:
        raise HTTPException(status_code=500, detail="Job was not persisted")

    return _serialize_job(job)


@app.post("/jobs/test", status_code=202)
def create_test_job():
    task = celery_client.send_task("tasks.healthcheck")

    return {
        "job_id": task.id,
        "status": "queued",
    }


@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    try:
        job = get_persisted_job(job_id)
    except psycopg.errors.InvalidTextRepresentation as error:
        raise HTTPException(status_code=404, detail="Job not found") from error

    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    return _serialize_job(job)


@app.get("/health/storage")
def storage_health():
    try:
        config = oci.config.from_file(
            file_location=os.getenv(
                "OCI_CONFIG_FILE",
                "/.oci/config",
            ),
            profile_name=os.getenv(
                "OCI_CONFIG_PROFILE",
                "DEFAULT",
            ),
        )

        client = oci.object_storage.ObjectStorageClient(config)
        namespace = client.get_namespace().data

        raw_bucket = client.get_bucket(
            namespace,
            os.environ["OCI_RAW_BUCKET"],
        ).data

        results_bucket = client.get_bucket(
            namespace,
            os.environ["OCI_RESULTS_BUCKET"],
        ).data

        return {
            "status": "ok",
            "storage": "oci_object_storage",
            "buckets": {
                "raw": raw_bucket.name,
                "results": results_bucket.name,
            },
        }

    except oci.exceptions.ServiceError as error:
        return JSONResponse(
            status_code=503,
            content={
                "status": "error",
                "storage": "oci_object_storage",
                "http_status": error.status,
                "code": error.code,
            },
        )

    except Exception as error:
        return JSONResponse(
            status_code=503,
            content={
                "status": "error",
                "storage": "oci_object_storage",
                "code": type(error).__name__,
            },
        )
