"""
Celery configuration for notification service background tasks
"""

import os
import logging
from celery import Celery
from kombu import Queue

logger = logging.getLogger(__name__)


def _get_redis_backend_url():
    """Build Redis backend URL with Sentinel support"""
    use_sentinel = os.getenv("REDIS_SENTINEL_ENABLED", "true").lower() == "true"

    if use_sentinel:
        # Sentinel backend URL format: sentinel://host:port;sentinel://host2:port2
        sentinel_host = os.getenv("REDIS_SENTINEL_HOST", "rfs-redis-cluster.saasodoo.svc.cluster.local")
        sentinel_port = os.getenv("REDIS_SENTINEL_PORT", "26379")

        if "," in sentinel_host:
            sentinels = ";".join([f"sentinel://{h.strip()}:{sentinel_port}" for h in sentinel_host.split(",")])
        else:
            sentinels = f"sentinel://{sentinel_host}:{sentinel_port}"

        return sentinels
    else:
        redis_host = os.getenv("REDIS_HOST", "redis")
        redis_port = os.getenv("REDIS_PORT", "6379")
        db = os.getenv("REDIS_DB", "0")
        return f"redis://{redis_host}:{redis_port}/{db}"


# Create Celery app
celery_app = Celery(
    "notification_service",
    broker=f"amqp://{os.getenv('RABBITMQ_USER', 'saasodoo')}:{os.getenv('RABBITMQ_PASSWORD', 'saasodoo123')}@{os.getenv('RABBITMQ_HOST', 'rabbitmq')}:{os.getenv('RABBITMQ_PORT', '5672')}/{os.getenv('RABBITMQ_VHOST', 'saasodoo')}",
    backend=_get_redis_backend_url(),
    include=['app.tasks.email', 'app.tasks.bulk']
)

# Configure Sentinel transport options if using Sentinel
if os.getenv("REDIS_SENTINEL_ENABLED", "true").lower() == "true":
    celery_app.conf.result_backend_transport_options = {
        'master_name': os.getenv("REDIS_SENTINEL_MASTER", "mymaster"),
        'db': int(os.getenv("REDIS_DB", "0"))
    }

# Define queues as quorum queues for durability
celery_app.conf.task_queues = (
    Queue('notification_email', queue_arguments={'x-queue-type': 'quorum'}),
    Queue('notification_bulk', queue_arguments={'x-queue-type': 'quorum'}),
)

# Configuration
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=5 * 60,  # 5 minutes max per email task
    task_soft_time_limit=4 * 60,  # 4 minutes soft limit
    worker_prefetch_multiplier=1,  # One task at a time for reliability
    task_acks_late=True,  # Acknowledge after task completion
    worker_disable_rate_limits=False,

    # Quorum queue compatibility - CRITICAL for RabbitMQ quorum queues
    # Auto-detect quorum queues and disable global QoS (required for quorum queues)
    worker_detect_quorum_queues=True,
    # Quorum queues require confirm_publish
    broker_transport_options={'confirm_publish': True},

    task_routes={
        'app.tasks.email.*': {'queue': 'notification_email'},
        'app.tasks.bulk.*': {'queue': 'notification_bulk'},
    },
    # Allow retries for transient SMTP errors
    task_retry_jitter=True,
    task_max_retries=3,
    task_default_retry_delay=30,  # 30 second delay between retries
)


if __name__ == '__main__':
    celery_app.start()
