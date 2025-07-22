"""
Celery configuration for instance service background tasks
"""

import os
from celery import Celery

# Create Celery app
celery_app = Celery(
    "instance_service",
    broker=f"amqp://{os.getenv('RABBITMQ_USER', 'saasodoo')}:{os.getenv('RABBITMQ_PASSWORD', 'saasodoo123')}@rabbitmq:5672/saasodoo",
    backend=f"redis://redis:6379/0",
    include=['app.tasks.provisioning', 'app.tasks.lifecycle', 'app.tasks.maintenance', 'app.tasks.monitoring']
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
    },
    # No automatic retry - admin manual retry only
    task_retry_jitter=False,
    task_max_retries=0,
)

if __name__ == '__main__':
    celery_app.start()