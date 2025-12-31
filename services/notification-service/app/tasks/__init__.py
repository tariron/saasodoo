"""Notification service Celery tasks"""

from app.tasks.email import send_email_task, send_template_email_task
from app.tasks.bulk import send_bulk_email_task

__all__ = [
    'send_email_task',
    'send_template_email_task',
    'send_bulk_email_task',
]
