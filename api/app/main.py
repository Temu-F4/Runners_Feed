import os
import hmac
import logging
import math
import secrets
from contextlib import asynccontextmanager
from typing import Literal
from urllib.parse import parse_qs, urlparse
from uuid import UUID, uuid4

import oci
import psycopg
from celery import Celery
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from redis import Redis
from starlette.concurrency import run_in_threadpool

from app.database import (
    create_account_session,
    create_guest_session,
    create_job,
    create_mobile_auth_exchange,
    create_mobile_oauth_transaction,
    delete_account_session,
    delete_guest_session,
    delete_user_data,
    consume_mobile_auth_exchange,
    consume_mobile_oauth_transaction,
    get_job as get_persisted_job,
    get_job_stages,
    get_model_quality_summary,
    get_user_profile,
    initialize_database,
    link_kakao_account,
    list_jobs as list_persisted_jobs,
    list_user_artifacts,
    mark_job_dispatch_failed,
    renew_active_account_session,
    renew_active_guest_session,
    update_user_profile,
)
from app.account_identity import (
    ACCOUNT_COOKIE_NAME,
    OAUTH_STATE_COOKIE_NAME,
    fetch_kakao_profile,
    issue_account_identity,
    kakao_authorization_url,
    kakao_login_configured,
    new_oauth_state,
    renew_account_identity,
    set_account_cookie,
    set_oauth_state_cookie,
)
from app.guest_identity import (
    GUEST_COOKIE_NAME,
    hash_guest_token,
    issue_guest_identity,
    renew_guest_identity,
    set_guest_cookie,
)
from app.mobile_identity import (
    hash_mobile_value,
    issue_mobile_exchange,
    issue_mobile_state,
    mobile_kakao_login_configured,
    mobile_kakao_redirect_uri,
    mobile_redirect,
)
from app.object_storage import ObjectStorageGateway, load_oci_config


LOGGER = logging.getLogger(__name__)

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

SUPPORTED_VIDEO_CONTENT_TYPES = {
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
}


def _model_id() -> str:
    return os.getenv("COACH_MODEL_ID", "sehyeon-57e4938").strip()


def _model_release() -> str:
    return os.getenv("MODEL_RELEASE", "local").strip()


def _video_suffix(filename: str) -> str | None:
    normalized = filename.lower()
    return next(
        (
            suffix
            for suffix in SUPPORTED_VIDEO_CONTENT_TYPES
            if normalized.endswith(suffix)
        ),
        None,
    )


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    yield


app = FastAPI(
    title="Runners Feed API",
    lifespan=lifespan,
)


def _bearer_token(request: Request) -> str | None:
    authorization = request.headers.get("Authorization", "").strip()
    scheme, separator, token = authorization.partition(" ")
    if not separator or scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


@app.middleware("http")
async def require_api_key(request: Request, call_next):
    if request.url.path in {"/health", "/metrics"} or request.method == "OPTIONS":
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

    is_mobile = request.url.path.startswith("/mobile/v1")
    bearer_token = _bearer_token(request)
    account_cookie_token = request.cookies.get(ACCOUNT_COOKIE_NAME)
    account_token = account_cookie_token or bearer_token
    user_id = None
    account = None
    account_identity = None
    clear_invalid_account_cookie = False
    invalid_bearer = False
    if account_token:
        try:
            account_identity = renew_account_identity(account_token)
            account = await run_in_threadpool(
                renew_active_account_session,
                token_hash=account_identity.token_hash,
                expires_at=account_identity.expires_at,
            )
            if account is not None:
                user_id = account["user_id"]
            else:
                account_identity = None
                if bearer_token and account_token == bearer_token:
                    invalid_bearer = True
                else:
                    clear_invalid_account_cookie = True
        except ValueError:
            account_identity = None
            if bearer_token and account_token == bearer_token:
                invalid_bearer = True
            else:
                clear_invalid_account_cookie = True

    guest_cookie_token = request.cookies.get(GUEST_COOKIE_NAME)
    guest_token = guest_cookie_token or (
        bearer_token if user_id is None else None
    )
    response_identity = None
    if user_id is None and guest_token:
        try:
            response_identity = renew_guest_identity(guest_token)
            guest_user_id = await run_in_threadpool(
                renew_active_guest_session,
                token_hash=response_identity.token_hash,
                expires_at=response_identity.expires_at,
            )
            if guest_user_id is not None:
                user_id = guest_user_id
            elif bearer_token and guest_token == bearer_token:
                invalid_bearer = True
        except ValueError:
            # Replace malformed or oversized cookies with a valid identity.
            user_id = None
            response_identity = None

    if user_id is None:
        if invalid_bearer:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid mobile session"},
            )
        if not is_mobile:
            response_identity = issue_guest_identity()
            user_id = await run_in_threadpool(
                create_guest_session,
                token_hash=response_identity.token_hash,
                expires_at=response_identity.expires_at,
            )
    request.state.user_id = user_id
    request.state.account = account
    request.state.account_token_hash = (
        account_identity.token_hash if account_identity is not None else None
    )
    request.state.guest_token_hash = (
        hash_guest_token(guest_token)
        if guest_token and user_id is not None and account is None
        else None
    )
    request.state.mobile_bearer = bool(bearer_token)
    request.state.bearer_token = bearer_token
    response = await call_next(request)
    delete_identity_cookies = getattr(
        request.state, "delete_identity_cookies", False
    )
    delete_guest_cookie = getattr(
        request.state, "delete_guest_cookie", False
    )
    if is_mobile or bearer_token:
        return response
    if delete_identity_cookies:
        response.delete_cookie(
            key=GUEST_COOKIE_NAME,
            path="/",
            secure=True,
            httponly=True,
            samesite="lax",
        )
        response.delete_cookie(
            key=ACCOUNT_COOKIE_NAME,
            path="/",
            secure=True,
            httponly=True,
            samesite="lax",
        )
    elif delete_guest_cookie:
        response.delete_cookie(
            key=GUEST_COOKIE_NAME,
            path="/",
            secure=True,
            httponly=True,
            samesite="lax",
        )
    elif response_identity is not None:
        set_guest_cookie(response, response_identity)
    if (
        account_identity is not None
        and not delete_identity_cookies
        and not getattr(request.state, "suppress_account_cookie", False)
    ):
        set_account_cookie(response, account_identity)
    elif clear_invalid_account_cookie and not delete_identity_cookies:
        response.delete_cookie(
            key=ACCOUNT_COOKIE_NAME,
            path="/",
            secure=True,
            httponly=True,
            samesite="lax",
        )
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


def _quality_int(name: str, default: int) -> int:
    value = int(os.getenv(name, str(default)))
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def _quality_float(name: str, default: float) -> float:
    value = float(os.getenv(name, str(default)))
    if not 0 <= value <= 1:
        raise ValueError(f"{name} must be between 0 and 1")
    return value


@app.get("/auth/kakao/start")
def start_kakao_login():
    state = new_oauth_state()
    try:
        destination = kakao_authorization_url(state)
    except RuntimeError as error:
        raise HTTPException(
            status_code=503,
            detail="Kakao login is not configured",
        ) from error
    response = RedirectResponse(destination, status_code=302)
    set_oauth_state_cookie(response, state)
    return response


@app.get("/auth/kakao/callback")
async def finish_kakao_login(
    request: Request,
    code: str | None = Query(default=None, max_length=2048),
    state: str | None = Query(default=None, max_length=512),
    error: str | None = Query(default=None, max_length=255),
):
    expected_state = request.cookies.get(OAUTH_STATE_COOKIE_NAME, "")
    state_valid = bool(
        state
        and expected_state
        and secrets.compare_digest(state, expected_state)
    )
    if error or not code or not state_valid:
        response = RedirectResponse("/?login=kakao-error", status_code=302)
        response.delete_cookie(
            key=OAUTH_STATE_COOKIE_NAME,
            path="/",
            secure=True,
            httponly=True,
            samesite="lax",
        )
        return response

    try:
        profile = await run_in_threadpool(fetch_kakao_profile, code)
        account_user_id = await run_in_threadpool(
            link_kakao_account,
            current_user_id=request.state.user_id,
            provider_user_id=profile.provider_user_id,
            email=profile.email,
            display_name=profile.display_name,
        )
        identity = issue_account_identity()
        await run_in_threadpool(
            create_account_session,
            token_hash=identity.token_hash,
            user_id=account_user_id,
            expires_at=identity.expires_at,
        )
    except Exception:
        LOGGER.exception("Kakao login callback failed")
        response = RedirectResponse("/?login=kakao-error", status_code=302)
    else:
        response = RedirectResponse("/?login=kakao-success", status_code=302)
        set_account_cookie(response, identity)
        request.state.delete_guest_cookie = True
        request.state.suppress_account_cookie = True

    response.delete_cookie(
        key=OAUTH_STATE_COOKIE_NAME,
        path="/",
        secure=True,
        httponly=True,
        samesite="lax",
    )
    return response


@app.get("/me")
def get_me(request: Request):
    account = request.state.account
    if account is None:
        return {
            "authenticated": False,
            "provider": None,
            "kakao_login_enabled": kakao_login_configured(),
        }
    return {
        "authenticated": True,
        "provider": account["provider"],
        "email": account["email"],
        "display_name": account["display_name"],
        "kakao_login_enabled": kakao_login_configured(),
    }


@app.post("/auth/logout")
def logout(request: Request):
    token_hash = request.state.account_token_hash
    if token_hash is not None:
        delete_account_session(token_hash)
    request.state.delete_identity_cookies = True
    return {"status": "logged_out"}


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
    def require_supported_video_object(cls, value: str) -> str:
        normalized = value.strip()
        if _video_suffix(normalized) is None:
            raise ValueError("input_object_name must reference an MP4 or MOV")
        return normalized


class CreateUploadRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content_type: Literal["video/mp4", "video/quicktime"]

    @field_validator("filename")
    @classmethod
    def require_supported_video_filename(cls, value: str) -> str:
        normalized = value.strip()
        if _video_suffix(normalized) is None:
            raise ValueError("filename must end with .mp4 or .mov")
        return normalized

    @model_validator(mode="after")
    def require_matching_content_type(self):
        suffix = _video_suffix(self.filename)
        if (
            suffix is None
            or self.content_type != SUPPORTED_VIDEO_CONTENT_TYPES[suffix]
        ):
            raise ValueError("content_type must match the video file extension")
        return self


class CompleteUploadRequest(BaseModel):
    object_name: str = Field(min_length=1, max_length=128)

    @field_validator("object_name")
    @classmethod
    def require_generated_upload_name(cls, value: str) -> str:
        normalized = value.strip()
        prefix = "uploads/"
        suffix = _video_suffix(normalized)
        if not normalized.startswith(prefix) or suffix is None:
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
    if object_name.startswith("uploads/"):
        suffix = _video_suffix(object_name)
        expected_content_type = (
            SUPPORTED_VIDEO_CONTENT_TYPES.get(suffix) if suffix else None
        )
        if metadata["content_type"] != expected_content_type:
            raise HTTPException(
                status_code=415,
                detail="Uploaded object content type does not match its extension",
            )

    return metadata


def _serialize_job(job: dict) -> dict:
    response = {
        "job_id": str(job["job_id"]),
        "case_id": job["case_id"],
        "input_object_name": job["input_object_name"],
        "height_snapshot_m": job["height_snapshot_m"],
        "model_id": job.get("model_id"),
        "model_release": job.get("model_release"),
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
            "skeleton": job["result_skeleton_object"],
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


class MobileJobRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    input_object_name: str = Field(
        min_length=1,
        max_length=128,
        alias="inputObjectName",
    )
    user_height_cm: float | None = Field(
        default=None,
        ge=50,
        le=250,
        alias="userHeightCm",
    )
    case_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$",
        alias="caseId",
    )

    @field_validator("input_object_name")
    @classmethod
    def require_mobile_video_object(cls, value: str) -> str:
        normalized = value.strip()
        if _video_suffix(normalized) is None:
            raise ValueError("inputObjectName must reference an MP4 or MOV")
        return normalized


class MobileProfileRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    height_cm: float | None = Field(
        default=None,
        ge=50,
        le=250,
        alias="heightCm",
    )


class MobileExchangeRequest(BaseModel):
    code: str = Field(min_length=1, max_length=512)


def _require_mobile_user(request: Request) -> UUID:
    user_id = getattr(request.state, "user_id", None)
    if user_id is None or not getattr(request.state, "mobile_bearer", False):
        raise HTTPException(
            status_code=401,
            detail="A mobile bearer session is required",
        )
    return user_id


def _mobile_profile(request: Request, user_id: UUID) -> dict:
    profile = get_user_profile(user_id)
    if profile is None:
        raise HTTPException(status_code=401, detail="User session is invalid")
    is_account = request.state.account is not None
    return {
        "userId": str(profile["user_id"]),
        "sessionType": "account" if is_account else "guest",
        "authenticated": is_account,
        "provider": profile.get("provider"),
        "email": profile.get("email"),
        "displayName": profile.get("display_name"),
        "heightCm": (
            round(float(profile["profile_height_m"]) * 100, 1)
            if profile.get("profile_height_m") is not None
            else None
        ),
        "kakaoLoginEnabled": mobile_kakao_login_configured(),
    }


def _mobile_stage(job: dict) -> tuple[str, float | None]:
    status = job["status"]
    if status == "SUCCESS":
        return "result", 100.0
    if status == "QUEUED":
        return "queue", None

    stages = get_job_stages(str(job["job_id"]))
    if not stages:
        return "queue", None

    stage_name = {
        "input_download": "upload",
        "video_analysis": "keypoints",
        "feature_extract": "features",
        "report_generate": "validation",
        "result_upload": "validation",
        "workspace_cleanup": "validation",
    }
    failed = next(
        (
            stage
            for stage in reversed(stages)
            if stage.get("status") in {"FAILED", "ERROR"}
        ),
        None,
    )
    running = next(
        (stage for stage in stages if stage.get("status") == "RUNNING"),
        None,
    )
    selected = failed or running or next(
        (
            stage
            for stage in reversed(stages)
            if stage.get("status") == "SUCCESS"
        ),
        stages[0],
    )
    if status in {"FAILED", "ERROR"}:
        return stage_name.get(selected.get("stage_key"), "validation"), None
    if running is None and not any(stage.get("status") == "SUCCESS" for stage in stages):
        return "queue", None
    return stage_name.get(selected.get("stage_key"), "validation"), None


def _mobile_job(job: dict) -> dict:
    stage, progress = _mobile_stage(job)
    status = job["status"]
    result = {
        "jobId": str(job["job_id"]),
        "title": job["case_id"],
        "caseId": job["case_id"],
        "status": status,
        "stage": stage,
        "progressPct": progress,
        "estimatedCompletionSeconds": None,
        "createdAt": job["created_at"],
        "startedAt": job["started_at"],
        "completedAt": job["completed_at"],
        "updatedAt": job["updated_at"],
        "heightCm": (
            round(float(job["height_snapshot_m"]) * 100, 1)
            if job.get("height_snapshot_m") is not None
            else None
        ),
        "modelId": job.get("model_id"),
        "modelRelease": job.get("model_release"),
        "error": (
            job.get("error_code") or "coach_failed"
            if status in {"FAILED", "ERROR"}
            else None
        ),
    }
    result["postureScore"] = None
    if status == "SUCCESS" and job.get("result_report_object"):
        try:
            report = ObjectStorageGateway().load_result_json(job["result_report_object"])
            result["postureScore"] = _finite_number(
                report.get("posture_score", report.get("postureScore"))
            ) if isinstance(report, dict) else None
        except Exception:
            LOGGER.warning("Unable to load score summary for %s", job.get("job_id"), exc_info=True)
    return result


def _finite_number(value: object) -> float | None:
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return float(value)
    return None


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def _mobile_reference_range(reference: object, unit: str) -> dict | None:
    if not isinstance(reference, dict):
        return None
    minimum = _finite_number(reference.get("min"))
    maximum = _finite_number(reference.get("max"))
    if minimum is None or maximum is None or maximum <= minimum:
        return None
    kind = reference.get("kind")
    if kind not in {"recommended", "reference"}:
        kind = "reference"
    criterion_version = reference.get("criterion_version", reference.get("criterionVersion"))
    return {
        "kind": kind,
        "min": minimum,
        "max": maximum,
        "unit": reference.get("unit") if isinstance(reference.get("unit"), str) else unit,
        "criterionVersion": criterion_version if isinstance(criterion_version, str) else None,
        "evidenceIds": _string_list(reference.get("evidence_ids", reference.get("evidenceIds", []))),
    }


def _mobile_feature(metric: dict, raw: dict, notice: str) -> dict | None:
    feature_id = metric.get("id")
    if not isinstance(feature_id, str) or not feature_id.strip():
        return None
    unit = metric.get("unit") if isinstance(metric.get("unit"), str) else ""
    metric_value = _finite_number(metric.get("value"))
    raw_value = _finite_number(raw.get("representative_value", raw.get("value")))
    representative_value = metric_value if metric_value is not None else raw_value
    confidence_pct = _finite_number(raw.get("confidence_pct", raw.get("confidencePct")))
    confidence_level = raw.get("confidence_level", raw.get("confidenceLevel"))
    if confidence_level not in {"high", "medium", "low", "excluded"}:
        confidence_level = "excluded"
    verdict = raw.get("verdict")
    if verdict not in {"improve", "maintain", "review", "excluded", "unavailable"}:
        verdict = "review"
    priority = raw.get("priority")
    if not isinstance(priority, int) or priority < 1:
        priority = None
    series = []
    raw_series = raw.get("series", [])
    if isinstance(raw_series, list):
        for point in raw_series:
            if not isinstance(point, dict) or not isinstance(point.get("frame_index", point.get("frameIndex")), int):
                continue
            series.append(
                {
                    "frameIndex": point.get("frame_index", point.get("frameIndex")),
                    "timestampMs": _finite_number(point.get("timestamp_ms", point.get("timestampMs"))),
                    "value": _finite_number(point.get("value")),
                    "confidencePct": _finite_number(point.get("confidence_pct", point.get("confidencePct"))),
                }
            )
    interpretation = raw.get("interpretation")
    coaching_action = raw.get("coaching_action", raw.get("coachingAction"))
    limitation = raw.get("limitation")
    score = _finite_number(raw.get("score"))
    score_method = raw.get("score_method", raw.get("scoreMethod"))
    confidence_assumed = raw.get("confidence_assumed", raw.get("confidenceAssumed")) is True
    visualization = raw.get("visualization")
    if not isinstance(visualization, dict):
        visualization = None
    return {
        "featureId": feature_id,
        "label": metric.get("label") if isinstance(metric.get("label"), str) else feature_id,
        "priority": priority,
        "verdict": verdict,
        "representativeValue": representative_value,
        "unit": unit,
        "aggregation": raw.get("aggregation") if isinstance(raw.get("aggregation"), str) else "reported",
        "referenceRange": _mobile_reference_range(raw.get("reference_range", raw.get("referenceRange")), unit),
        "series": series,
        "interpretation": interpretation if isinstance(interpretation, str) else "",
        "coachingAction": coaching_action if isinstance(coaching_action, str) else None,
        "confidencePct": confidence_pct,
        "confidenceLevel": confidence_level,
        "limitation": limitation if isinstance(limitation, str) else notice,
        "evidenceIds": _string_list(raw.get("evidence_ids", raw.get("evidenceIds", []))),
        "score": score,
        "scoreMethod": score_method if isinstance(score_method, str) else None,
        "denominatorPolicy": raw.get("denominator_policy", raw.get("denominatorPolicy")),
        "goodFrameCount": raw.get("good_frame_count", raw.get("goodFrameCount")),
        "evaluatedFrameCount": raw.get("evaluated_frame_count", raw.get("evaluatedFrameCount")),
        "sourceFrameCount": raw.get("source_frame_count", raw.get("sourceFrameCount")),
        "evaluationCoveragePct": _finite_number(raw.get("evaluation_coverage_pct", raw.get("evaluationCoveragePct"))),
        "confidenceAssumed": confidence_assumed,
        "visualization": visualization,
    }


def _mobile_action(action: object, kind: str) -> dict | None:
    if not isinstance(action, dict) or not isinstance(action.get("text"), str):
        return None
    feature_id = action.get("feature_id", action.get("featureId"))
    if not isinstance(feature_id, str):
        return None
    reference = action.get("measurement_reference", action.get("measurementReference"))
    measurement = None
    if isinstance(reference, dict):
        measurement = {
            "value": _finite_number(reference.get("value")),
            "unit": reference.get("unit") if isinstance(reference.get("unit"), str) else "",
            "referenceMin": _finite_number(reference.get("reference_min", reference.get("referenceMin"))),
            "referenceMax": _finite_number(reference.get("reference_max", reference.get("referenceMax"))),
        }
    return {"featureId": feature_id, "kind": kind, "text": action["text"], "measurementReference": measurement}


def _mobile_exercise_video(item: object) -> dict | None:
    if not isinstance(item, dict):
        return None
    video_id, title, value = item.get("id"), item.get("title"), item.get("url")
    if not all(isinstance(field, str) and field.strip() for field in (video_id, title, value)):
        return None
    parsed = urlparse(value)
    if parsed.scheme != "https" or parsed.hostname != "www.youtube.com" or parsed.path != "/watch":
        return None
    if not parse_qs(parsed.query).get("v"):
        return None
    feature_id = item.get("feature_id", item.get("feature"))
    feature_id = {
        "Amplitude of pelvis oscillation": "feature1",
        "Elbow angle": "feature2",
        "Trunk flexion angle": "feature3",
        "Postural lean angle": "feature4",
    }.get(feature_id, feature_id)
    return {
        "id": video_id,
        "title": title,
        "url": value,
        "featureId": feature_id if isinstance(feature_id, str) else None,
    }


def _mobile_evidence(item: object, index: int) -> dict | None:
    if not isinstance(item, dict):
        return None
    source = item.get("source") if isinstance(item.get("source"), dict) else {}
    evidence_id = item.get("evidence_id", item.get("evidenceId", item.get("id")))
    if not isinstance(evidence_id, str) or not evidence_id:
        evidence_id = f"evidence-{index + 1}"
    year = source.get("year", item.get("year"))
    media_uri = item.get("uri", item.get("frame_uri", item.get("frameUri")))
    source_url = source.get("url") or item.get("url")
    doi = source.get("doi") or item.get("doi")
    return {
        "evidenceId": evidence_id,
        "frameIndex": item.get("frame_index", item.get("frameIndex")) if isinstance(item.get("frame_index", item.get("frameIndex")), int) else None,
        "timestampMs": _finite_number(item.get("timestamp_ms", item.get("timestampMs"))),
        "uri": media_uri if isinstance(media_uri, str) else None,
        "title": source.get("title") or item.get("title") or item.get("label") or "근거",
        "authors": source.get("authors") or item.get("authors") or "",
        "year": year if isinstance(year, int) else None,
        "doi": doi if isinstance(doi, str) else None,
        "url": source_url if isinstance(source_url, str) else None,
        "page": item.get("page") if isinstance(item.get("page"), int) else source.get("page") if isinstance(source.get("page"), int) else None,
        "section": item.get("section") or source.get("section"),
        "criterionVersion": item.get("criterion_version", item.get("criterionVersion", source.get("criterion_version", source.get("criterionVersion")))) if isinstance(item.get("criterion_version", item.get("criterionVersion", source.get("criterion_version", source.get("criterionVersion")))), str) else None,
        "excerptSummary": item.get("excerpt_summary") or item.get("description") or item.get("text") or "",
        "caveat": item.get("caveat") or source.get("caveat") or "",
        "metadata": item,
    }


def _mobile_result(job: dict, report: dict) -> dict:
    raw_features = report.get("features", {})
    raw_features = raw_features if isinstance(raw_features, dict) else {}
    metrics = report.get("metrics", [])
    features = []
    if isinstance(metrics, list):
        for metric in metrics:
            if not isinstance(metric, dict):
                continue
            metric_id = metric.get("id")
            raw = raw_features.get(metric_id, {}) if isinstance(metric_id, str) else {}
            notice = report.get("notice", "측정 조건에 따라 결과가 달라질 수 있습니다.")
            feature = _mobile_feature(metric, raw if isinstance(raw, dict) else {}, notice if isinstance(notice, str) else "측정 조건에 따라 결과가 달라질 수 있습니다.")
            if feature is not None:
                features.append(feature)

    raw_narrative = report.get("narrative", {})
    raw_narrative = raw_narrative if isinstance(raw_narrative, dict) else {}
    raw_priority = raw_narrative.get("priority_actions", raw_narrative.get("priorityActions", []))
    raw_maintain = raw_narrative.get("maintain_actions", raw_narrative.get("maintainActions", []))
    priority_actions = [_mobile_action(action, "improve") for action in raw_priority] if isinstance(raw_priority, list) else []
    maintain_actions = [_mobile_action(action, "maintain") for action in raw_maintain] if isinstance(raw_maintain, list) else []
    narrative_status = "success" if raw_narrative.get("status") == "success" else "unavailable"
    narrative = {
        "status": narrative_status,
        "errorCode": raw_narrative.get("error_code", raw_narrative.get("errorCode")) if narrative_status == "unavailable" and isinstance(raw_narrative.get("error_code", raw_narrative.get("errorCode")), str) else None,
        "model": raw_narrative.get("model") if isinstance(raw_narrative.get("model"), str) else None,
        "summary": raw_narrative.get("overall_summary", raw_narrative.get("summary")) if isinstance(raw_narrative.get("overall_summary", raw_narrative.get("summary")), str) else None,
        "priorityActions": [action for action in priority_actions if action is not None],
        "maintainActions": [action for action in maintain_actions if action is not None],
        "exerciseVideos": [video for item in raw_narrative.get(
            "exercise_videos", raw_narrative.get("exerciseVideos", [])
        ) if (video := _mobile_exercise_video(item)) is not None],
        "disclaimer": raw_narrative.get("disclaimer", "이 내용은 러닝 동작 참고용이며 의료 진단이나 부상 예측이 아닙니다."),
        "validatorVersion": raw_narrative.get("validator_version", raw_narrative.get("validatorVersion", "unvalidated")),
    }
    video = report.get("video", {}) if isinstance(report.get("video", {}), dict) else {}
    tracking = report.get("tracking", {}) if isinstance(report.get("tracking", {}), dict) else {}
    raw_run_metrics = report.get("run_metrics", report.get("runMetrics"))
    raw_run_metrics = raw_run_metrics if isinstance(raw_run_metrics, dict) else {}
    pace = raw_run_metrics.get("pace_per_km", raw_run_metrics.get("pacePerKm"))
    basis = raw_run_metrics.get("estimation_basis", raw_run_metrics.get("estimationBasis"))
    run_metrics = {
        "pacePerKm": pace if isinstance(pace, str) else None,
        "cadenceSpm": _finite_number(raw_run_metrics.get("cadence_spm", raw_run_metrics.get("cadenceSpm"))),
        "strideLengthM": _finite_number(raw_run_metrics.get("stride_length_m", raw_run_metrics.get("strideLengthM"))),
        "estimationBasis": basis if isinstance(basis, str) else None,
    }
    evidence = [_mobile_evidence(item, index) for index, item in enumerate(report.get("evidence", []) if isinstance(report.get("evidence", []), list) else [])]
    runtime = report.get("runtime_metadata", report.get("runtimeMetadata"))
    runtime = runtime if isinstance(runtime, dict) else {}
    return {
        "jobId": str(job["job_id"]),
        "modelId": job.get("model_id"),
        "modelRelease": job.get("model_release"),
        "createdAt": job["created_at"],
        "completedAt": job["completed_at"],
        "analyzedFrameCount": tracking.get("tracked_frames", 0),
        "totalFrameCount": tracking.get("total_frames", video.get("frame_count", 0)),
        "features": features,
        "evidence": [item for item in evidence if item is not None],
        "narrative": narrative,
        "postureScore": _finite_number(report.get("posture_score", report.get("postureScore"))),
        "runMetrics": run_metrics,
        # Signed media URLs are intentionally minted on demand by result-video-url.
        "media": None,
        "runtimeMetadata": {
            "promptVersion": runtime.get("prompt_version", runtime.get("promptVersion")) if isinstance(runtime.get("prompt_version", runtime.get("promptVersion")), str) else None,
            "model": runtime.get("model") if isinstance(runtime.get("model"), str) else None,
            "validatorVersion": runtime.get("validator_version", runtime.get("validatorVersion")) if isinstance(runtime.get("validator_version", runtime.get("validatorVersion")), str) else None,
            "inputTokens": _finite_number(runtime.get("input_tokens", runtime.get("inputTokens"))),
            "outputTokens": _finite_number(runtime.get("output_tokens", runtime.get("outputTokens"))),
        },
    }


def _mobile_signals(features: list[dict]) -> list[dict]:
    return [
        {
            "featureId": feature["featureId"],
            "label": feature["label"],
            "priority": feature["priority"],
            "verdict": feature["verdict"],
            "value": feature["representativeValue"],
            "unit": feature["unit"],
            "referenceRange": feature["referenceRange"],
            "message": feature["interpretation"] or feature["limitation"],
            "confidencePct": feature["confidencePct"],
            "confidenceLevel": feature["confidenceLevel"],
            "confidenceAssumed": feature.get("confidenceAssumed", False),
            "score": feature.get("score"),
        }
        for feature in features
    ]


def _mobile_dashboard_insights(jobs: list[dict]) -> tuple[list[dict], list[dict], dict | None]:
    successful = [job for job in jobs if job.get("status") == "SUCCESS" and job.get("result_report_object")]
    if successful:
        latest = successful[0]
        successful = [
            job for job in successful
            if job.get("model_id") == latest.get("model_id")
            and job.get("model_release") == latest.get("model_release")
        ]
    successful.sort(key=lambda job: str(job.get("completed_at") or job.get("created_at") or ""))
    results: list[tuple[dict, dict]] = []
    for job in successful:
        try:
            report = ObjectStorageGateway().load_result_json(job["result_report_object"])
            results.append((job, _mobile_result(job, report)))
        except Exception:
            LOGGER.warning("Unable to load mobile dashboard report for %s", job.get("job_id"), exc_info=True)
    if not results:
        return [], [], None
    latest_features = results[-1][1]["features"]
    latest_signals = _mobile_signals(latest_features)
    priority = sorted(
        [signal for signal in latest_signals if signal["verdict"] == "improve" and signal["priority"] is not None],
        key=lambda signal: signal["priority"],
    )
    by_feature: dict[str, list[tuple[dict, dict]]] = {}
    for job, result in results:
        for feature in result["features"]:
            if feature["representativeValue"] is not None:
                by_feature.setdefault(feature["featureId"], []).append((job, feature))
    trend = None
    candidates = sorted(by_feature.items(), key=lambda item: len(item[1]), reverse=True)
    if candidates and len(candidates[0][1]) >= 8:
        feature_id, points = candidates[0]
        first = points[0][1]["representativeValue"]
        last = points[-1][1]["representativeValue"]
        delta = None if first in {None, 0} or last is None else round((last - first) / abs(first) * 100, 2)
        trend = {
            "featureId": feature_id,
            "label": points[-1][1]["label"],
            "unit": points[-1][1]["unit"],
            "points": [{"recordedAt": job.get("completed_at") or job.get("created_at"), "value": feature["representativeValue"]} for job, feature in points],
            "deltaPct": delta,
            "summary": None,
        }
    return priority, latest_signals, trend


@app.post("/mobile/v1/sessions/guest")
def create_mobile_guest_session(request: Request):
    existing_user_id = getattr(request.state, "user_id", None)
    existing_token = getattr(request.state, "bearer_token", None)
    if (
        existing_user_id is not None
        and existing_token
        and request.state.guest_token_hash is not None
    ):
        identity = renew_guest_identity(existing_token)
        return {
            "accessToken": existing_token,
            "tokenType": "Bearer",
            "sessionType": "guest",
            "expiresAt": identity.expires_at,
        }
    identity = issue_guest_identity()
    user_id = create_guest_session(
        token_hash=identity.token_hash,
        expires_at=identity.expires_at,
    )
    return {
        "accessToken": identity.token,
        "tokenType": "Bearer",
        "sessionType": "guest",
        "userId": str(user_id),
        "expiresAt": identity.expires_at,
    }


@app.post("/mobile/v1/auth/kakao/start")
def start_mobile_kakao_login(request: Request):
    user_id = _require_mobile_user(request)
    if not mobile_kakao_login_configured():
        raise HTTPException(status_code=503, detail="Mobile Kakao login is not configured")
    try:
        state = issue_mobile_state()
        create_mobile_oauth_transaction(
            state_hash=state.value_hash,
            user_id=user_id,
            expires_at=state.expires_at,
        )
        authorization_url = kakao_authorization_url(
            state.value,
            redirect_uri=mobile_kakao_redirect_uri(),
        )
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail="Mobile Kakao login is not configured") from error
    return {
        "authorizationUrl": authorization_url,
        "expiresAt": state.expires_at,
    }


@app.get("/mobile/v1/auth/kakao/callback")
async def finish_mobile_kakao_login(
    code: str | None = Query(default=None, max_length=2048),
    state: str | None = Query(default=None, max_length=512),
    error: str | None = Query(default=None, max_length=255),
):
    if error or not code or not state:
        return RedirectResponse(mobile_redirect(error="kakao_login_failed"), status_code=302)
    current_user_id = await run_in_threadpool(
        consume_mobile_oauth_transaction,
        hash_mobile_value(state),
    )
    if current_user_id is None:
        return RedirectResponse(mobile_redirect(error="invalid_or_expired_state"), status_code=302)
    try:
        profile = await run_in_threadpool(
            fetch_kakao_profile,
            code,
            redirect_uri=mobile_kakao_redirect_uri(),
        )
        account_user_id = await run_in_threadpool(
            link_kakao_account,
            current_user_id=current_user_id,
            provider_user_id=profile.provider_user_id,
            email=profile.email,
            display_name=profile.display_name,
        )
        exchange = issue_mobile_exchange()
        await run_in_threadpool(
            create_mobile_auth_exchange,
            code_hash=exchange.value_hash,
            user_id=account_user_id,
            expires_at=exchange.expires_at,
        )
    except Exception:
        LOGGER.exception("Mobile Kakao login callback failed")
        return RedirectResponse(mobile_redirect(error="kakao_login_failed"), status_code=302)
    return RedirectResponse(mobile_redirect(code=exchange.value), status_code=302)


@app.post("/mobile/v1/auth/kakao/exchange")
def exchange_mobile_kakao_code(payload: MobileExchangeRequest):
    user_id = consume_mobile_auth_exchange(hash_mobile_value(payload.code))
    if user_id is None:
        raise HTTPException(status_code=400, detail="Invalid or expired exchange code")
    identity = issue_account_identity()
    create_account_session(
        token_hash=identity.token_hash,
        user_id=user_id,
        expires_at=identity.expires_at,
    )
    return {
        "accessToken": identity.token,
        "tokenType": "Bearer",
        "sessionType": "account",
        "expiresAt": identity.expires_at,
    }


@app.get("/mobile/v1/me")
def mobile_me(request: Request):
    return _mobile_profile(request, _require_mobile_user(request))


@app.patch("/mobile/v1/me/profile")
def update_mobile_profile(
    payload: MobileProfileRequest,
    request: Request,
):
    user_id = _require_mobile_user(request)
    profile_height_m = (
        payload.height_cm / 100 if payload.height_cm is not None else None
    )
    update_user_profile(
        user_id=user_id,
        profile_height_m=profile_height_m,
    )
    return _mobile_profile(request, user_id)


@app.post("/mobile/v1/auth/logout")
def mobile_logout(request: Request):
    _require_mobile_user(request)
    if request.state.account_token_hash is not None:
        delete_account_session(request.state.account_token_hash)
    if request.state.guest_token_hash is not None:
        delete_guest_session(request.state.guest_token_hash)
    return {"status": "logged_out"}


@app.get("/mobile/v1/dashboard")
def mobile_dashboard(request: Request):
    user_id = _require_mobile_user(request)
    jobs = list_persisted_jobs(user_id=user_id, limit=20)
    active = next(
        (job for job in jobs if job["status"] in {"QUEUED", "PROCESSING"}),
        None,
    )
    priority_signals, latest_signals, trend = _mobile_dashboard_insights(jobs)
    return {
        "profile": _mobile_profile(request, user_id),
        "activeJob": _mobile_job(active) if active else None,
        "jobs": [_mobile_job(job) for job in jobs],
        "prioritySignals": priority_signals,
        "latestSignals": latest_signals,
        "trend": trend,
    }


@app.post("/mobile/v1/uploads", status_code=201)
def create_mobile_upload(payload: CreateUploadRequest, request: Request):
    _require_mobile_user(request)
    return create_upload(payload)


@app.post("/mobile/v1/uploads/complete")
def complete_mobile_upload(
    payload: CompleteUploadRequest,
    request: Request,
):
    _require_mobile_user(request)
    return complete_upload(payload)


@app.post("/mobile/v1/jobs", status_code=202)
def create_mobile_job(payload: MobileJobRequest, request: Request):
    user_id = _require_mobile_user(request)
    profile = get_user_profile(user_id)
    height_cm = payload.user_height_cm
    if height_cm is None and profile is not None:
        stored_height = profile.get("profile_height_m")
        height_cm = float(stored_height) * 100 if stored_height is not None else None
    if height_cm is None:
        raise HTTPException(status_code=422, detail="userHeightCm is required")
    raw_job = create_coach_job(
        CreateCoachJobRequest(
            case_id=payload.case_id or f"analysis-{uuid4().hex[:12]}",
            input_object_name=payload.input_object_name,
            user_height_m=height_cm / 100,
        ),
        request,
    )
    job = get_persisted_job(job_id=raw_job["job_id"], user_id=user_id)
    if job is None:
        raise HTTPException(status_code=500, detail="Mobile job was not persisted")
    return _mobile_job(job)


@app.get("/mobile/v1/jobs")
def list_mobile_jobs(
    request: Request,
    limit: int = Query(default=20, ge=1, le=50),
):
    user_id = _require_mobile_user(request)
    jobs = list_persisted_jobs(user_id=user_id, limit=limit)
    return {"jobs": [_mobile_job(job) for job in jobs], "nextCursor": None}


@app.get("/mobile/v1/jobs/{job_id}")
def get_mobile_job(job_id: str, request: Request):
    job = _get_owned_job_or_404(job_id, _require_mobile_user(request))
    return _mobile_job(job)


@app.post("/mobile/v1/jobs/{job_id}/result-video-url")
def create_mobile_result_url(job_id: str, request: Request):
    _require_mobile_user(request)
    result = create_result_url(job_id, request)
    return {
        "jobId": result["job_id"],
        "renderedVideoUrl": result["rendered_video_url"],
        "expiresAt": result["expires_at"],
    }


@app.get("/mobile/v1/jobs/{job_id}/result")
def get_mobile_result(job_id: str, request: Request):
    user_id = _require_mobile_user(request)
    job = _get_owned_job_or_404(job_id, user_id)
    if job["status"] != "SUCCESS":
        raise HTTPException(status_code=409, detail="Result is not available yet")
    report_object = job["result_report_object"]
    if not report_object:
        raise HTTPException(status_code=404, detail="Analysis result is unavailable")
    try:
        report = ObjectStorageGateway().load_result_json(report_object)
    except Exception as error:
        raise HTTPException(status_code=503, detail="Failed to load analysis result") from error
    return _mobile_result(job, report)


@app.delete("/mobile/v1/me/data")
def delete_mobile_data(request: Request):
    _require_mobile_user(request)
    return delete_my_data(request)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/metrics", response_class=PlainTextResponse)
def metrics():
    try:
        summary = get_model_quality_summary(
            window_minutes=_quality_int("MODEL_QUALITY_WINDOW_MINUTES", 60),
            max_processing_seconds=_quality_int(
                "MODEL_QUALITY_MAX_PROCESSING_SECONDS", 3600
            ),
            model_id=_model_id(),
            model_release=_model_release(),
        )
    except Exception:
        LOGGER.exception("Failed to collect model metrics")
        return PlainTextResponse(
            "# HELP runners_feed_model_metrics_up Whether model metrics are available.\n"
            "# TYPE runners_feed_model_metrics_up gauge\n"
            "runners_feed_model_metrics_up 0\n",
            status_code=503,
        )

    completed = int(summary.get("completed_count") or 0)
    success = int(summary.get("success_count") or 0)
    failure = int(summary.get("failure_count") or 0)
    invalid = int(summary.get("invalid_result_count") or 0)
    stale = int(summary.get("stale_processing_count") or 0)
    success_rate = success / completed if completed else 1.0
    failure_rate = failure / completed if completed else 0.0
    average = summary.get("average_processing_seconds")
    lines = [
        "# HELP runners_feed_model_metrics_up Whether model metrics are available.",
        "# TYPE runners_feed_model_metrics_up gauge",
        "runners_feed_model_metrics_up 1",
        "# HELP runners_feed_model_completed_count Completed jobs in the quality window.",
        "# TYPE runners_feed_model_completed_count gauge",
        f"runners_feed_model_completed_count {completed}",
        "# HELP runners_feed_model_success_count Successful jobs in the quality window.",
        "# TYPE runners_feed_model_success_count gauge",
        f"runners_feed_model_success_count {success}",
        "# HELP runners_feed_model_failure_count Failed jobs in the quality window.",
        "# TYPE runners_feed_model_failure_count gauge",
        f"runners_feed_model_failure_count {failure}",
        "# HELP runners_feed_model_invalid_result_count Jobs rejected by artifact validation.",
        "# TYPE runners_feed_model_invalid_result_count gauge",
        f"runners_feed_model_invalid_result_count {invalid}",
        "# HELP runners_feed_model_stale_processing_count Jobs exceeding the processing budget.",
        "# TYPE runners_feed_model_stale_processing_count gauge",
        f"runners_feed_model_stale_processing_count {stale}",
        "# HELP runners_feed_model_success_rate Success rate in the quality window.",
        "# TYPE runners_feed_model_success_rate gauge",
        f"runners_feed_model_success_rate {success_rate}",
        "# HELP runners_feed_model_failure_rate Failure rate in the quality window.",
        "# TYPE runners_feed_model_failure_rate gauge",
        f"runners_feed_model_failure_rate {failure_rate}",
        "# HELP runners_feed_model_average_processing_seconds Average processing time in seconds.",
        "# TYPE runners_feed_model_average_processing_seconds gauge",
        f"runners_feed_model_average_processing_seconds {float(average or 0)}",
    ]
    return PlainTextResponse("\n".join(lines) + "\n")


@app.get("/health/model-quality")
def model_quality_health():
    window_minutes = _quality_int("MODEL_QUALITY_WINDOW_MINUTES", 60)
    min_sample_size = _quality_int("MODEL_QUALITY_MIN_SAMPLE_SIZE", 3)
    max_processing_seconds = _quality_int(
        "MODEL_QUALITY_MAX_PROCESSING_SECONDS", 3600
    )
    min_success_rate = _quality_float("MODEL_QUALITY_MIN_SUCCESS_RATE", 0.95)
    max_failure_rate = _quality_float("MODEL_QUALITY_MAX_FAILURE_RATE", 0.10)
    summary = get_model_quality_summary(
        window_minutes=window_minutes,
        max_processing_seconds=max_processing_seconds,
        model_id=_model_id(),
        model_release=_model_release(),
    )
    completed_count = int(summary.get("completed_count") or 0)
    success_count = int(summary.get("success_count") or 0)
    failure_count = int(summary.get("failure_count") or 0)
    invalid_result_count = int(summary.get("invalid_result_count") or 0)
    stale_processing_count = int(summary.get("stale_processing_count") or 0)
    success_rate = success_count / completed_count if completed_count else None
    failure_rate = failure_count / completed_count if completed_count else None
    average_processing_seconds = summary.get("average_processing_seconds")
    if average_processing_seconds is not None:
        average_processing_seconds = float(average_processing_seconds)
    conditions: list[str] = []
    if stale_processing_count:
        conditions.append("long_processing_detected")
    if invalid_result_count:
        conditions.append("invalid_result_artifact_detected")
    if completed_count >= min_sample_size:
        if success_rate is not None and success_rate < min_success_rate:
            conditions.append("success_rate_below_threshold")
        if failure_rate is not None and failure_rate > max_failure_rate:
            conditions.append("failure_rate_above_threshold")
    status = "rollback_required" if conditions else (
        "insufficient_sample" if completed_count < min_sample_size else "ok"
    )
    payload = {
        "status": status,
        "modelId": _model_id(),
        "modelRelease": _model_release(),
        "rollbackConditionsTriggered": conditions,
        "windowMinutes": window_minutes,
        "thresholds": {
            "minSampleSize": min_sample_size,
            "maxProcessingSeconds": max_processing_seconds,
            "minSuccessRate": min_success_rate,
            "maxFailureRate": max_failure_rate,
        },
        "observed": {
            "completedCount": completed_count,
            "successCount": success_count,
            "failureCount": failure_count,
            "invalidResultCount": invalid_result_count,
            "staleProcessingCount": stale_processing_count,
            "successRate": success_rate,
            "failureRate": failure_rate,
            "averageProcessingSeconds": average_processing_seconds,
        },
    }
    if conditions:
        return JSONResponse(status_code=503, content=payload)
    return payload


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
def create_upload(request: CreateUploadRequest):
    suffix = _video_suffix(request.filename)
    if suffix is None:  # The request model validates this before the handler.
        raise HTTPException(status_code=422, detail="Unsupported video format")
    object_name = f"uploads/{uuid4().hex}{suffix}"

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
        "required_headers": {"Content-Type": request.content_type},
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
    input_metadata = _inspect_input_object(payload.input_object_name)
    input_etag = input_metadata.get("etag")
    if not isinstance(input_etag, str) or not input_etag:
        raise HTTPException(status_code=503, detail="Uploaded video ETag is unavailable")
    job_id = str(uuid4())

    create_job(
        job_id=job_id,
        case_id=payload.case_id,
        input_object_name=payload.input_object_name,
        input_size_bytes=int(input_metadata["size_bytes"]),
        input_etag=input_etag,
        user_id=request.state.user_id,
        height_snapshot_m=payload.user_height_m,
        model_id=_model_id(),
        model_release=_model_release(),
    )

    try:
        celery_client.send_task(
            "coach.dispatch_video_analysis",
            args=[job_id],
            task_id=job_id,
            queue="gpu_dispatch",
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


@app.get("/jobs/{job_id}/skeleton")
def get_job_skeleton(job_id: str, request: Request):
    job = _get_owned_job_or_404(job_id, request.state.user_id)
    if job["status"] != "SUCCESS":
        raise HTTPException(
            status_code=409,
            detail="Skeleton is not available until the job succeeds",
        )

    skeleton_object = job["result_skeleton_object"]
    if not skeleton_object:
        raise HTTPException(
            status_code=404,
            detail="Skeleton replay is not available for this job",
        )

    try:
        return ObjectStorageGateway().load_result_gzip_json(skeleton_object)
    except oci.exceptions.ServiceError as error:
        if error.status == 404:
            raise HTTPException(
                status_code=404,
                detail="Skeleton replay has expired",
            ) from error
        raise HTTPException(
            status_code=503,
            detail="Failed to load skeleton replay",
        ) from error
    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail="Failed to load skeleton replay",
        ) from error


@app.delete("/me/data")
def delete_my_data(request: Request):
    user_id = request.state.user_id
    storage = ObjectStorageGateway()

    try:
        for artifact in list_user_artifacts(user_id):
            input_name = artifact.get("input_object_name")
            if input_name:
                storage.delete_input(input_name)
            for field in (
                "result_details_object",
                "result_predictions_object",
                "result_report_object",
                "result_skeleton_object",
                "result_video_object",
            ):
                object_name = artifact.get(field)
                if object_name:
                    storage.delete_result(object_name)
        delete_user_data(user_id)
    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail="Failed to delete all user data",
        ) from error

    request.state.delete_identity_cookies = True
    return {"status": "deleted"}


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
