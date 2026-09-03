import os
import hmac
from contextlib import asynccontextmanager
from typing import Literal
from uuid import UUID, uuid4

import oci
import psycopg
from celery import Celery
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from redis import Redis
from starlette.concurrency import run_in_threadpool

from app.database import (
    create_guest_session,
    create_job,
    find_active_guest_user,
    get_job as get_persisted_job,
    initialize_database,
    list_jobs as list_persisted_jobs,
    mark_job_dispatch_failed,
)
from app.guest_identity import (
    GUEST_COOKIE_NAME,
    hash_guest_token,
    issue_guest_identity,
    set_guest_cookie,
)
from app.object_storage import ObjectStorageGateway, load_oci_config


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


@app.middleware("http")
async def require_api_key(request: Request, call_next):
    if request.url.path == "/health" or request.method == "OPTIONS":
        return await call_next(request)

    expected_key = os.getenv("API_KEY")
    if not expected_key:
        return JSONResponse(
            status_code=503,
            content={"detail": "API authentication is not configured"},
        )

    provided_key = request.headers.get("X-API-Key", "")
    if not hmac.compare_digest(provided_key, expected_key):
        return JSONResponse(
            status_code=401,
            content={"detail": "Invalid API key"},
        )

    # Dependency health checks remain API-key protected, but do not create a
    # guest account for infrastructure probes.
    if request.url.path.startswith("/health"):
        return await call_next(request)

    guest_token = request.cookies.get(GUEST_COOKIE_NAME)
    user_id = None
    if guest_token:
        try:
            token_hash = hash_guest_token(guest_token)
            user_id = await run_in_threadpool(
                find_active_guest_user,
                token_hash,
            )
        except ValueError:
            # Replace malformed or oversized cookies with a valid identity.
            user_id = None

    issued_identity = None
    if user_id is None:
        issued_identity = issue_guest_identity()
        user_id = await run_in_threadpool(
            create_guest_session,
            token_hash=issued_identity.token_hash,
            expires_at=issued_identity.expires_at,
        )

    request.state.user_id = user_id
    response = await call_next(request)
    if issued_identity is not None:
        set_guest_cookie(response, issued_identity)
    return response


def _result_url_ttl_seconds() -> int:
    ttl_seconds = int(os.getenv("RESULT_URL_TTL_SECONDS", "900"))
    if not 60 <= ttl_seconds <= 3600:
        raise ValueError(
            "RESULT_URL_TTL_SECONDS must be between 60 and 3600"
        )
    return ttl_seconds


def _upload_url_ttl_seconds() -> int:
    ttl_seconds = int(os.getenv("UPLOAD_URL_TTL_SECONDS", "900"))
    if not 60 <= ttl_seconds <= 3600:
        raise ValueError(
            "UPLOAD_URL_TTL_SECONDS must be between 60 and 3600"
        )
    return ttl_seconds


def _max_upload_bytes() -> int:
    max_bytes = int(os.getenv("MAX_UPLOAD_BYTES", "262144000"))
    if max_bytes <= 0:
        raise ValueError("MAX_UPLOAD_BYTES must be positive")
    return max_bytes


class CreateCoachJobRequest(BaseModel):
    case_id: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$",
    )
    input_object_name: str = Field(
        min_length=1,
        max_length=1024,
    )
    user_height_m: float = Field(ge=0.5, le=2.5)

    @field_validator("input_object_name")
    @classmethod
    def require_mp4_object(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized.lower().endswith(".mp4"):
            raise ValueError("input_object_name must reference an MP4")
        return normalized


class CreateUploadRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content_type: Literal["video/mp4"] = "video/mp4"

    @field_validator("filename")
    @classmethod
    def require_mp4_filename(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized.lower().endswith(".mp4"):
            raise ValueError("filename must end with .mp4")
        return normalized


class CompleteUploadRequest(BaseModel):
    object_name: str = Field(min_length=1, max_length=128)

    @field_validator("object_name")
    @classmethod
    def require_generated_upload_name(cls, value: str) -> str:
        normalized = value.strip()
        prefix = "uploads/"
        suffix = ".mp4"
        if not normalized.startswith(prefix) or not normalized.endswith(suffix):
            raise ValueError("object_name must be a generated upload path")

        identifier = normalized[len(prefix) : -len(suffix)]
        if len(identifier) != 32:
            raise ValueError("object_name must be a generated upload path")
        try:
            int(identifier, 16)
        except ValueError as error:
            raise ValueError(
                "object_name must be a generated upload path"
            ) from error
        return normalized


def _inspect_input_object(object_name: str) -> dict[str, object]:
    try:
        metadata = ObjectStorageGateway().inspect_input_object(object_name)
    except oci.exceptions.ServiceError as error:
        if error.status == 404:
            raise HTTPException(
                status_code=404,
                detail="Uploaded video was not found",
            ) from error
        raise HTTPException(
            status_code=503,
            detail="Failed to inspect uploaded video",
        ) from error
    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail="Failed to inspect uploaded video",
        ) from error

    size_bytes = int(metadata["size_bytes"])
    if size_bytes <= 0:
        raise HTTPException(status_code=400, detail="Uploaded video is empty")
    if size_bytes > _max_upload_bytes():
        raise HTTPException(
            status_code=413,
            detail="Uploaded video exceeds the size limit",
        )
    if (
        object_name.startswith("uploads/")
        and metadata["content_type"] != "video/mp4"
    ):
        raise HTTPException(
            status_code=415,
            detail="Uploaded object must have content type video/mp4",
        )

    return metadata


def _serialize_job(job: dict) -> dict:
    response = {
        "job_id": str(job["job_id"]),
        "case_id": job["case_id"],
        "input_object_name": job["input_object_name"],
        "height_snapshot_m": job["height_snapshot_m"],
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
            "report": job["result_report_object"],
            "rendered_video": job["result_video_object"],
        }

    if job["status"] == "FAILED":
        response["error"] = job["error_code"] or "coach_failed"

    return response


def _get_owned_job_or_404(job_id: str, user_id: UUID) -> dict:
    try:
        job = get_persisted_job(job_id=job_id, user_id=user_id)
    except psycopg.errors.InvalidTextRepresentation as error:
        raise HTTPException(status_code=404, detail="Job not found") from error

    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    return job


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


@app.post("/uploads", status_code=201)
def create_upload(_: CreateUploadRequest):
    object_name = f"uploads/{uuid4().hex}.mp4"

    try:
        upload_url, expires_at = (
            ObjectStorageGateway().create_input_write_url(
                object_name=object_name,
                ttl_seconds=_upload_url_ttl_seconds(),
            )
        )
    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail="Failed to create upload URL",
        ) from error

    return {
        "object_name": object_name,
        "upload_url": upload_url,
        "method": "PUT",
        "required_headers": {"Content-Type": "video/mp4"},
        "expires_at": expires_at,
        "max_size_bytes": _max_upload_bytes(),
    }


@app.post("/uploads/complete")
def complete_upload(request: CompleteUploadRequest):
    metadata = _inspect_input_object(request.object_name)
    return {
        "status": "ready",
        "object_name": request.object_name,
        **metadata,
    }


@app.post("/jobs", status_code=202)
def create_coach_job(
    payload: CreateCoachJobRequest,
    request: Request,
):
    _inspect_input_object(payload.input_object_name)
    job_id = str(uuid4())

    create_job(
        job_id=job_id,
        case_id=payload.case_id,
        input_object_name=payload.input_object_name,
        user_id=request.state.user_id,
        height_snapshot_m=payload.user_height_m,
    )

    try:
        celery_client.send_task(
            "coach.run_object_storage",
            args=[
                payload.case_id,
                payload.input_object_name,
                payload.user_height_m,
            ],
            task_id=job_id,
            queue="coach",
        )
    except Exception as error:
        mark_job_dispatch_failed(job_id)
        raise HTTPException(
            status_code=503,
            detail="Failed to dispatch coach job",
        ) from error

    job = get_persisted_job(
        job_id=job_id,
        user_id=request.state.user_id,
    )
    if job is None:
        raise HTTPException(status_code=500, detail="Job was not persisted")

    return _serialize_job(job)


@app.get("/jobs")
def list_jobs(
    request: Request,
    limit: int = Query(default=20, ge=1, le=50),
):
    jobs = list_persisted_jobs(
        user_id=request.state.user_id,
        limit=limit,
    )
    return {"jobs": [_serialize_job(job) for job in jobs]}


@app.get("/jobs/{job_id}")
def get_job(job_id: str, request: Request):
    job = _get_owned_job_or_404(job_id, request.state.user_id)
    return _serialize_job(job)


@app.post("/jobs/{job_id}/result-url")
def create_result_url(job_id: str, request: Request):
    job = _get_owned_job_or_404(job_id, request.state.user_id)
    if job["status"] != "SUCCESS":
        raise HTTPException(
            status_code=409,
            detail="Result is not available until the job succeeds",
        )

    result_object = job["result_video_object"]
    if not result_object:
        raise HTTPException(
            status_code=409,
            detail="Rendered video is not available",
        )

    try:
        url, expires_at = ObjectStorageGateway().create_result_read_url(
            object_name=result_object,
            ttl_seconds=_result_url_ttl_seconds(),
        )
    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail="Failed to create result URL",
        ) from error

    return {
        "job_id": str(job["job_id"]),
        "rendered_video_url": url,
        "expires_at": expires_at,
    }


@app.get("/jobs/{job_id}/report")
def get_job_report(job_id: str, request: Request):
    job = _get_owned_job_or_404(job_id, request.state.user_id)
    if job["status"] != "SUCCESS":
        raise HTTPException(
            status_code=409,
            detail="Report is not available until the job succeeds",
        )

    report_object = job["result_report_object"]
    if not report_object:
        raise HTTPException(
            status_code=409,
            detail="Analysis report is not available",
        )

    try:
        return ObjectStorageGateway().load_result_json(report_object)
    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail="Failed to load analysis report",
        ) from error


@app.get("/health/storage")
def storage_health():
    try:
        config = load_oci_config()

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
