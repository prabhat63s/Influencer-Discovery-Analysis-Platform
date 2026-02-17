"""
Celery Application Configuration
===============================
This is the entry point for the background worker process.
It defines:
1. The Broker URL (Redis) - Where tasks are sent.
2. The Backend URL (Redis) - Where results are stored.
3. Task Modules - The Python files that contain @celery.task functions.

Run the Worker from terminal:
$ celery -A app.config.celery_app worker --loglevel=info
"""
import os
from celery import Celery
from app.config.settings import settings

# 1. Define the Broker URL
REDIS_URL = settings.REDIS_URL

# 2. Initialize Celery App
celery_app = Celery(
    "creatorconnect_worker",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["app.worker.tasks"]
)

# 3. Configure Settings
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Worker Settings
    worker_concurrency=4,  # Number of parallel processes
    worker_prefetch_multiplier=1,  # One task at a time per worker (prevents hoarding)
    
    # Redis Connection Settings (Robustness)
    broker_connection_retry_on_startup=True,
    broker_pool_limit=None,  # Do not limit connection pool (let Redis handle it)
    
    # Result Backend Settings
    result_backend_transport_options={
        "retry_policy": {
            "max_retries": 20,
            "interval_start": 0,
            "interval_step": 0.2,
            "interval_max": 2.0,
        },
        "health_check_interval": 10,
    },
)

if __name__ == "__main__":
    celery_app.start()
