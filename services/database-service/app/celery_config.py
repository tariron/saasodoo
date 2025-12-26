"""
Celery configuration for database service background tasks
Handles asynchronous database pool provisioning, health monitoring, and cleanup
"""

import os
import structlog
from celery import Celery
from kombu import Queue

logger = structlog.get_logger(__name__)


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
    "database_service",
    broker=f"amqp://{os.getenv('RABBITMQ_USER', 'saasodoo')}:{os.getenv('RABBITMQ_PASSWORD', 'saasodoo123')}@{os.getenv('RABBITMQ_HOST', 'rabbitmq')}:{os.getenv('RABBITMQ_PORT', '5672')}/{os.getenv('RABBITMQ_VHOST', 'saasodoo')}",
    backend=_get_redis_backend_url(),
    include=['app.tasks.provisioning', 'app.tasks.monitoring']
)

# Configure Sentinel transport options if using Sentinel
if os.getenv("REDIS_SENTINEL_ENABLED", "true").lower() == "true":
    celery_app.conf.result_backend_transport_options = {
        'master_name': os.getenv("REDIS_SENTINEL_MASTER", "mymaster"),
        'db': int(os.getenv("REDIS_DB", "0"))
    }

# Explicitly define queues as quorum queues for durability
celery_app.conf.task_queues = (
    Queue('database_provisioning', queue_arguments={'x-queue-type': 'quorum'}),
    Queue('database_monitoring', queue_arguments={'x-queue-type': 'quorum'}),
    Queue('database_maintenance', queue_arguments={'x-queue-type': 'quorum'}),
)

# Configuration
celery_app.conf.update(
    # Serialization
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',

    # Timezone
    timezone='UTC',
    enable_utc=True,

    # Task tracking
    task_track_started=True,
    result_expires=86400,  # Results expire after 24 hours

    # Time limits (database provisioning can take 2-3 minutes)
    task_time_limit=12 * 60,  # 12 minutes hard limit (for migrations)
    task_soft_time_limit=10 * 60,  # 10 minutes soft limit

    # Worker settings
    worker_prefetch_multiplier=1,  # Process one provisioning task at a time
    task_acks_late=True,  # Acknowledge after task completion for reliability
    worker_disable_rate_limits=False,

    # Quorum queue compatibility - CRITICAL for RabbitMQ 4.x quorum queues
    # Quorum queues don't support global QoS, only per-consumer QoS
    # This must be set to prevent "NOT_IMPLEMENTED" errors
    broker_pool_limit=None,  # Disable connection pooling for compatibility
    worker_send_task_events=False,

    # Task routing
    task_routes={
        'app.tasks.provisioning.*': {'queue': 'database_provisioning'},
        'app.tasks.monitoring.*': {'queue': 'database_monitoring'},
    },

    # Retry configuration
    # Most tasks retry automatically with exponential backoff
    task_retry_jitter=True,  # Add jitter to prevent thundering herd
    task_max_retries=3,  # Maximum 3 retries for transient failures
    task_default_retry_delay=60,  # 1 minute default retry delay

    # Beat schedule for periodic tasks
    beat_schedule={
        'health-check-pools': {
            'task': 'app.tasks.monitoring.health_check_db_pools',
            'schedule': 300.0,  # Every 5 minutes
            'options': {'queue': 'database_monitoring'}
        },
        'cleanup-failed-pools': {
            'task': 'app.tasks.monitoring.cleanup_failed_pools',
            'schedule': 86400.0,  # Daily at midnight (with beat scheduler timezone)
            'options': {'queue': 'database_maintenance'}
        },
    },
)


if __name__ == '__main__':
    celery_app.start()
