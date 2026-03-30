"""Celery application configuration for async task processing."""

from celery import Celery
from src.config import settings

# Create Celery app
celery_app = Celery(
    'notification_orchestration',
    broker=settings.redis_url,
    backend=settings.redis_url
)

# Configuration
celery_app.conf.update(
    task_serializer='json',
    result_serializer='json',
    accept_content=['json'],
    timezone='UTC',
    enable_utc=True,

    # Priority queues
    task_routes={
        'tasks.send_notification_critical': {'queue': 'critical', 'priority': 10},
        'tasks.send_notification_high': {'queue': 'high', 'priority': 7},
        'tasks.send_notification_medium': {'queue': 'medium', 'priority': 5},
        'tasks.send_notification_low': {'queue': 'low', 'priority': 3},
    },

    # Retry configuration
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,

    # Result expiration
    result_expires=3600,

    # Task time limits
    task_time_limit=300,  # 5 minutes hard limit
    task_soft_time_limit=240,  # 4 minutes soft limit
)

# Auto-discover tasks
celery_app.autodiscover_tasks(['src.tasks'])
