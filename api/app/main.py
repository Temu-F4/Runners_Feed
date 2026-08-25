import os
from celery import Celery
import oci

import psycopg
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from redis import Redis

app = FastAPI(title="Runners Feed API")
celery_client = Celery(
    "runners_feed_api",
    broker=os.getenv("CELERY_BROKER_URL", "redis://redis:6379/1"),
    backend=os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/2"),
)

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

@app.post("/jobs/test", status_code=202)
def create_test_job():
    task = celery_client.send_task("tasks.healthcheck")

    return {
        "job_id": task.id,
        "status": "queued",
    }


@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    task = celery_client.AsyncResult(job_id)

    response = {
        "job_id": job_id,
        "status": task.state,
    }

    if task.successful():
        response["result"] = task.result

    elif task.failed():
        response["error"] = "worker_task_failed"

    return response
@app.get("/health/storage")
def storage_health():
    try:
        config = oci.config.from_file(
            file_location=os.getenv(
                "OCI_CONFIG_FILE",
                "/root/.oci/config",
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
