import os

from celery import Celery
from celery.signals import worker_init

from runpod_client import client_from_environment


celery_app = Celery(
    "runners_feed_coach",
    broker=os.getenv("CELERY_BROKER_URL", "redis://redis:6379/1"),
    backend=os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/2"),
    include=["coach_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Seoul",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_time_limit=3600,
    task_soft_time_limit=3500,
    task_routes={
        "coach.dispatch_video_analysis": {
            "queue": "gpu_dispatch",
        },
        "coach.run_postprocess": {
            "queue": "postprocess",
        },
    },
)


@worker_init.connect
def validate_runpod_configuration(**_: object) -> None:
    """Fail worker startup before it can accept jobs with invalid credentials."""
    client_from_environment()
