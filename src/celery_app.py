"""Celery application configuration for async task processing."""

import logging
from celery import Celery
from celery.signals import worker_process_init
from src.config import settings
from src.utils.logger import configure_logging

configure_logging(settings.log_level)
logger = logging.getLogger(__name__)

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
        'inbound.process_inbound_message': {'queue': 'medium', 'priority': 6},
        'inbound.retry_stuck_messages': {'queue': 'low', 'priority': 2},
        'retention.clean_expired_inbound_data': {'queue': 'low', 'priority': 1},
    },

    # Retry configuration
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    worker_hijack_root_logger=False,
    broker_connection_retry_on_startup=True,

    # Result expiration
    result_expires=3600,

    # Task time limits
    task_time_limit=300,  # 5 minutes hard limit
    task_soft_time_limit=240,  # 4 minutes soft limit
    
    # Periodic tasks (beat schedule)
    beat_schedule={
        'retry-stuck-inbound-messages': {
            'task': 'inbound.retry_stuck_messages',
            'schedule': 300.0,  # Run every 5 minutes
        },
    },
)

# Auto-discover tasks
celery_app.autodiscover_tasks(['src.tasks'])

import asyncio
from typing import Optional

_SHARED_TASK_LOOP: Optional[asyncio.AbstractEventLoop] = None

def get_shared_task_loop() -> asyncio.AbstractEventLoop:
    """
    Return a process-local shared event loop for Celery task execution.
    Reusing one loop avoids cross-loop issues with async DB connection pools.
    """
    global _SHARED_TASK_LOOP
    if _SHARED_TASK_LOOP is None or _SHARED_TASK_LOOP.is_closed():
        _SHARED_TASK_LOOP = asyncio.new_event_loop()
        asyncio.set_event_loop(_SHARED_TASK_LOOP)
    return _SHARED_TASK_LOOP


@worker_process_init.connect
def init_celery_worker(**kwargs):
    """
    Ensure the async SQLAlchemy engine is properly disposed and recreated
    after a Celery worker forks.
    """
    import asyncio
    from src.core.database import engine
    
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
    loop.run_until_complete(engine.dispose())
    logger.info("Celery worker process initialized")
