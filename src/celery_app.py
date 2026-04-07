"""Celery application - currently disabled, using direct async/await instead."""

# Celery is not active. All notification delivery uses async/await directly.
# Uncomment below to re-enable when a Celery worker is needed.

# from celery import Celery
# from src.config import settings
#
# celery_app = Celery(
#     'notification_orchestration',
#     broker=settings.redis_url,
#     backend=settings.redis_url
# )
#
# celery_app.conf.update(
#     task_serializer='json',
#     result_serializer='json',
#     accept_content=['json'],
#     timezone='UTC',
#     enable_utc=True,
#     task_routes={
#         'tasks.send_notification_critical': {'queue': 'critical', 'priority': 10},
#         'tasks.send_notification_high': {'queue': 'high', 'priority': 7},
#         'tasks.send_notification_medium': {'queue': 'medium', 'priority': 5},
#         'tasks.send_notification_low': {'queue': 'low', 'priority': 3},
#     },
#     task_acks_late=True,
#     task_reject_on_worker_lost=True,
#     worker_prefetch_multiplier=1,
#     result_expires=3600,
#     task_time_limit=300,
#     task_soft_time_limit=240,
# )
#
# celery_app.autodiscover_tasks(['src.tasks'])
