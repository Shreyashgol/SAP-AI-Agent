from celery import Celery
from celery.schedules import crontab
from celery.signals import setup_logging

from app.core.settings import get_settings

settings = get_settings()

celery_app = Celery(
    "sap_ai_platform",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "app.worker.tasks.discovery",
        "app.worker.tasks.semantic",
        "app.worker.tasks.knowledge_graph",
        "app.worker.tasks.tools",
        "app.worker.tasks.embedding",
        "app.worker.tasks.document",
        "app.worker.tasks.report",
        "app.worker.tasks.monitoring",
    ],
)

celery_app.conf.update(
    # Tasks declare queue="default" / queue="discovery"; make the worker consume
    # them without needing an explicit -Q flag (celery only listens to its
    # default queue otherwise, and queued tasks would never run).
    task_default_queue="default",
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    result_expires=86400,  # 24 hours
    # RedBeat scheduler key prefix
    redbeat_key_prefix="redbeat:",
    # Nightly scheduled tasks (TR-004: weight recalculation at 02:00 UTC)
    beat_schedule={
        "nightly-tool-weight-recalc": {
            "task": "tools.recalculate_weights",
            "schedule": crontab(hour=2, minute=0),
            "kwargs": {"tenant_id": "system"},  # dispatcher task iterates all tenants
        },
    },
)


@setup_logging.connect
def on_setup_logging(**kwargs: object) -> None:
    # Let structlog handle logging, not Celery's default
    pass
