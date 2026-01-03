"""
Celery configuration for instance service background tasks
"""

import os
import logging
from celery import Celery
from celery.signals import worker_ready
from kombu import Queue

logger = logging.getLogger(__name__)


def _get_redis_backend_url():
    """Build Redis backend URL with Sentinel support"""
    use_sentinel = os.getenv("REDIS_SENTINEL_ENABLED", "true").lower() == "true"

    if use_sentinel:
        # Sentinel backend URL format: sentinel://host:port;sentinel://host2:port2
        # Master name and db go in transport_options, NOT in the URL
        sentinel_host = os.getenv("REDIS_SENTINEL_HOST", "rfs-redis-cluster.saasodoo.svc.cluster.local")
        sentinel_port = os.getenv("REDIS_SENTINEL_PORT", "26379")

        # Parse comma-separated hosts if provided
        if "," in sentinel_host:
            sentinels = ";".join([f"sentinel://{h.strip()}:{sentinel_port}" for h in sentinel_host.split(",")])
        else:
            sentinels = f"sentinel://{sentinel_host}:{sentinel_port}"

        return sentinels
    else:
        # Direct Redis connection
        redis_host = os.getenv("REDIS_HOST", "redis")
        redis_port = os.getenv("REDIS_PORT", "6379")
        db = os.getenv("REDIS_DB", "0")
        return f"redis://{redis_host}:{redis_port}/{db}"


# Create Celery app
celery_app = Celery(
    "instance_service",
    broker=f"amqp://{os.getenv('RABBITMQ_USER', 'saasodoo')}:{os.getenv('RABBITMQ_PASSWORD', 'saasodoo123')}@{os.getenv('RABBITMQ_HOST', 'rabbitmq')}:{os.getenv('RABBITMQ_PORT', '5672')}/{os.getenv('RABBITMQ_VHOST', 'saasodoo')}",
    backend=_get_redis_backend_url(),
    include=[
        'app.tasks.provisioning',
        'app.tasks.lifecycle',
        'app.tasks.maintenance',
        'app.tasks.monitoring',
        'app.tasks.migration',
        'app.tasks.backup',
        'app.tasks.restore',
        'app.tasks.upgrade',
    ]
)

# Configure Sentinel transport options if using Sentinel
if os.getenv("REDIS_SENTINEL_ENABLED", "true").lower() == "true":
    celery_app.conf.result_backend_transport_options = {
        'master_name': os.getenv("REDIS_SENTINEL_MASTER", "mymaster"),
        'db': int(os.getenv("REDIS_DB", "0"))
    }

# Explicitly define queues as quorum queues
celery_app.conf.task_queues = (
    Queue('instance_provisioning', queue_arguments={'x-queue-type': 'quorum'}),
    Queue('instance_operations', queue_arguments={'x-queue-type': 'quorum'}),
    Queue('instance_maintenance', queue_arguments={'x-queue-type': 'quorum'}),
    Queue('instance_monitoring', queue_arguments={'x-queue-type': 'quorum'}),
)

# Configuration
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,  # 30 minutes max per task
    task_soft_time_limit=25 * 60,  # 25 minutes soft limit
    worker_prefetch_multiplier=1,  # One task per worker at a time
    task_acks_late=True,  # Acknowledge after task completion
    worker_disable_rate_limits=False,
    task_routes={
        'app.tasks.provisioning.*': {'queue': 'instance_provisioning'},
        'app.tasks.lifecycle.*': {'queue': 'instance_operations'},
        'app.tasks.maintenance.*': {'queue': 'instance_maintenance'},
        'app.tasks.monitoring.*': {'queue': 'instance_monitoring'},
        'app.tasks.migration.*': {'queue': 'instance_maintenance'},
        'app.tasks.backup.*': {'queue': 'instance_maintenance'},
        'app.tasks.restore.*': {'queue': 'instance_maintenance'},
        'app.tasks.upgrade.*': {'queue': 'instance_maintenance'},
    },
    # No automatic retry - admin manual retry only
    task_retry_jitter=False,
    task_max_retries=0,
)


@worker_ready.connect
def start_monitoring_on_worker_ready(sender, **kwargs):
    """
    Start Docker event monitoring when Celery worker is ready.
    This ensures monitoring starts automatically when instance-worker restarts,
    not just when instance-service (FastAPI) restarts.
    """
    auto_start = os.getenv('AUTO_START_MONITORING', 'true').lower() == 'true'

    if auto_start:
        logger.info("Worker ready - auto-starting Docker event monitoring (delayed 5s)")
        from app.tasks.monitoring import monitor_docker_events_task

        try:
            # Delay 5s to ensure old workers are terminated during rolling updates
            task = monitor_docker_events_task.apply_async(countdown=5)
            logger.info(f"Docker event monitoring queued with 5s delay: {task.id}")
        except Exception as e:
            logger.error(f"Failed to start monitoring from worker: {e}")
    else:
        logger.info("Worker ready - monitoring auto-start disabled (AUTO_START_MONITORING=false)")


if __name__ == '__main__':
    celery_app.start()