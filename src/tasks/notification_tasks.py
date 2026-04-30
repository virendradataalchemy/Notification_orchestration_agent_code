"""Celery tasks for processing notifications with retry and failover."""

import asyncio
import time
import logging
import json
from datetime import datetime
from typing import Optional, Dict, Any
from uuid import UUID

from colorama import init, Fore, Style
from celery import Task
from sqlalchemy import select, text
from sqlalchemy.orm import selectinload

# Initialize colorama for Windows/Unix compatibility
init(autoreset=True)

from src.celery_app import celery_app
from src.core.database import AsyncSessionLocal
from src.models import (
    Notification,
    NotificationChannel,
    NotificationStatus,
    ChannelStatus,
    TenantProviderConfig,
)
from src.services.provider_manager import ProviderManager
from src.services.orchestration_agent import OrchestrationAgent
from src.services.channel_policy import get_provider_for_channel
from src.providers.base import Message, ProviderStatus

logger = logging.getLogger(__name__)
_TASK_EVENT_LOOP: Optional[asyncio.AbstractEventLoop] = None


def _is_retryable_channel_error(error_text: str) -> bool:
    """Return False for permanent/configuration errors that should not be retried."""
    msg = (error_text or "").lower()
    non_retryable_patterns = (
        "provider returned failure: 21910",
        "invalid from and to pair",
        "not configured",
        "no_from_number",
        "missing for channel",
    )
    if "provider " in msg and " not available for channel " in msg:
        return False
    return not any(pattern in msg for pattern in non_retryable_patterns)


def _get_or_create_task_loop() -> asyncio.AbstractEventLoop:
    """
    Return a process-local event loop for Celery task execution.

    Reusing one loop avoids cross-loop issues with async DB connection pools.
    """
    global _TASK_EVENT_LOOP
    if _TASK_EVENT_LOOP is None or _TASK_EVENT_LOOP.is_closed():
        _TASK_EVENT_LOOP = asyncio.new_event_loop()
    return _TASK_EVENT_LOOP


class NotificationTask(Task):
    """Base task with automatic retry configuration."""

    autoretry_for = (Exception,)
    retry_kwargs = {'max_retries': 3}
    retry_backoff = True
    retry_backoff_max = 125  # Max 125 seconds between retries
    retry_jitter = False


@celery_app.task(base=NotificationTask, name='tasks.send_notification_critical', bind=True)
def send_notification_critical(self, notification_id: str):
    """
    Send CRITICAL priority notification (immediate delivery).

    Max retries: 3
    Retry delays: 5s, 25s, 125s
    """
    logger.info(f"{Fore.MAGENTA}{Style.BRIGHT}[CRITICAL] Processing notification {notification_id}")
    return _send_notification_sync(notification_id, priority='critical')


@celery_app.task(base=NotificationTask, name='tasks.send_notification_high', bind=True)
def send_notification_high(self, notification_id: str):
    """
    Send HIGH priority notification (< 1 minute).

    Max retries: 3
    Retry delays: 5s, 25s, 125s
    """
    logger.info(f"{Fore.RED}{Style.BRIGHT}[HIGH] Processing notification {notification_id}")
    return _send_notification_sync(notification_id, priority='high')


@celery_app.task(base=NotificationTask, name='tasks.send_notification_medium', bind=True)
def send_notification_medium(self, notification_id: str):
    """
    Send MEDIUM priority notification (< 5 minutes).

    Max retries: 3
    Retry delays: 5s, 25s, 125s
    """
    logger.info(f"{Fore.YELLOW}{Style.BRIGHT}[MEDIUM] Processing notification {notification_id}")
    return _send_notification_sync(notification_id, priority='medium')


@celery_app.task(base=NotificationTask, name='tasks.send_notification_low', bind=True)
def send_notification_low(self, notification_id: str):
    """
    Send LOW priority notification (< 1 hour).

    Max retries: 2 (fewer retries for low priority)
    Retry delays: 5s, 25s
    """
    logger.info(f"{Fore.BLUE}{Style.BRIGHT}[LOW] Processing notification {notification_id}")
    return _send_notification_sync(notification_id, priority='low', max_attempts=2)


# def _send_notification_sync(
#     notification_id: str,
#     priority: str,
#     max_attempts: int = 3
# ) -> Dict[str, Any]:
#     """
#     Synchronous wrapper for async notification sending.

#     Celery tasks must be synchronous, but we use async database operations.
#     """
#     import asyncio

#     loop = asyncio.get_event_loop()
#     if loop.is_running():
#         # If already in async context, create new loop
#         loop = asyncio.new_event_loop()
#         asyncio.set_event_loop(loop)

#     try:
#         result = loop.run_until_complete(
#             _send_notification_async(notification_id, priority, max_attempts)
#         )
#         return result
#     finally:
#         if not loop.is_running():
#             loop.close()

def _send_notification_sync(
    notification_id: str,
    priority: str,
    max_attempts: int = 3
) -> Dict[str, Any]:
    """
    Synchronous wrapper for async notification sending.
    Handles event loop creation for Celery worker threads.
    """
    loop = _get_or_create_task_loop()
    asyncio.set_event_loop(loop)
    return loop.run_until_complete(
        _send_notification_async(notification_id, priority, max_attempts)
    )

async def _send_notification_async(
    notification_id: str,
    priority: str,
    max_attempts: int
) -> Dict[str, Any]:
    """
    Main async notification sending logic with retry and failover.

    Process:
    1. Load notification from database
    2. For each channel:
       - Get healthy provider
       - Attempt send with exponential backoff
       - On failure, try failover provider
       - Log all events
       - Update engagement stats
    """
    async with AsyncSessionLocal() as db:
        try:
            # Load notification with channels
            notification = await _load_notification(db, notification_id)

            if not notification:
                logger.error(f"Notification {notification_id} not found")
                return {'status': 'error', 'reason': 'not_found'}

            logger.info(
                f"Loaded notification {notification_id} for user {notification.user_id}, "
                f"channels: {[c.channel for c in notification.channels]}"
            )

            # Initialize managers
            provider_mgr = ProviderManager(db)
            orchestration_agent = OrchestrationAgent(db)
            notif_data = notification.data or {}
            delivery_mode = notif_data.get("delivery_mode", "parallel_all")
            channel_plan = notif_data.get("channel_plan", [])

            results = {}
            sequential_success = False

            if delivery_mode == "sequential_failover":
                results, sequential_success = await _process_channels_sequential(
                    db=db,
                    notification=notification,
                    channel_records=notification.channels,
                    provider_mgr=provider_mgr,
                    orchestration_agent=orchestration_agent,
                    max_attempts=max_attempts,
                    channel_plan=channel_plan
                )
            else:
                # Process channels in parallel-all mode (existing behavior)
                for channel_record in notification.channels:
                    channel = channel_record.channel

                    logger.info(f"{Fore.BLUE}Processing channel {channel} for notification {notification_id}")

                    result = await _send_via_channel(
                        db=db,
                        notification=notification,
                        channel_record=channel_record,
                        provider_mgr=provider_mgr,
                        orchestration_agent=orchestration_agent,
                        max_attempts=max_attempts
                    )

                    results[channel] = result

            # Determine overall notification status
            if delivery_mode == "sequential_failover":
                if sequential_success:
                    notification.status = NotificationStatus.DELIVERED
                    notification.delivered_at = datetime.utcnow()
                else:
                    notification.status = NotificationStatus.FAILED
                    notification.failed_at = datetime.utcnow()
            else:
                all_succeeded = all(r['status'] == 'success' for r in results.values())
                all_failed = all(r['status'] == 'failed' for r in results.values())

                if all_succeeded:
                    notification.status = NotificationStatus.DELIVERED
                    notification.delivered_at = datetime.utcnow()
                elif all_failed:
                    notification.status = NotificationStatus.FAILED
                    notification.failed_at = datetime.utcnow()
                else:
                    # Partial success
                    notification.status = NotificationStatus.SENT

            await db.commit()

            success_count = len([r for r in results.values() if r['status'] == 'success'])
            fail_count = len([r for r in results.values() if r['status'] == 'failed'])
            
            summary_color = Fore.GREEN if fail_count == 0 else (Fore.YELLOW if success_count > 0 else Fore.RED)

            logger.info(
                f"{summary_color}{Style.BRIGHT}Completed notification {notification_id}: "
                f"{success_count} succeeded, {fail_count} failed"
            )

            return {
                'notification_id': notification_id,
                'status': notification.status.value,
                'channels': results,
                'delivery_mode': delivery_mode
            }

        except Exception as e:
            logger.error(f"Fatal error processing notification {notification_id}: {e}", exc_info=True)
            await db.rollback()
            raise


async def _load_notification(db, notification_id: str):
    """Load notification with channels from database."""
    try:
        notification_uuid = UUID(notification_id)
    except ValueError:
        logger.error(f"Invalid notification ID format: {notification_id}")
        return None

    query = (
        select(Notification)
        .options(selectinload(Notification.channels))
        .where(Notification.id == notification_uuid)
    )
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def _send_via_channel(
    db,
    notification: Notification,
    channel_record: NotificationChannel,
    provider_mgr: ProviderManager,
    orchestration_agent: OrchestrationAgent,
    max_attempts: int
) -> Dict[str, Any]:
    """
    Send notification via specific channel with retry and failover.

    Retry delays: 5s, 25s, 125s (exponential backoff)
    Provider failover: Try backup provider on failure
    """
    channel = channel_record.channel
    delays = [5, 25, 125]  # Exponential backoff delays
    notification_id = notification.id
    tenant_id = notification.tenant_id
    user_id = notification.user_id

    # Get initial healthy provider
    provider = await provider_mgr.get_healthy_provider(channel)
    tenant_provider_config = await _get_tenant_provider_config(
        db=db,
        tenant_id=tenant_id,
        channel=channel,
    )
    _enforce_sender_identity(channel, tenant_provider_config)

    logger.info(f"Selected provider {provider} for channel {channel}")

    for attempt in range(max_attempts):
        start_time = time.time()

        try:
            # Log sending event
            await _log_event(
                db, notification_id, 'sending', channel, provider,
                {'attempt': attempt + 1, 'max_attempts': max_attempts}
            )

            # Get provider instance and send
            provider_instance = _get_provider_instance(channel, provider, tenant_provider_config)

            if not provider_instance:
                raise Exception(f"Provider {provider} not available for channel {channel}")

            message = _build_message(notification, channel)
            response = await provider_instance.send(message)

            elapsed_ms = int((time.time() - start_time) * 1000)

            # Check if successful
            if response.status == ProviderStatus.SUCCESS:
                # Update channel record
                channel_record.status = ChannelStatus.SENT
                channel_record.message_id = response.message_id
                channel_record.attempts = attempt + 1

                # Update notification timestamps
                if not notification.sent_at:
                    notification.sent_at = datetime.utcnow()

                # Log success event
                await _log_event(
                    db, notification_id, 'sent', channel, provider,
                    {
                        'message_id': response.message_id,
                        'latency_ms': elapsed_ms,
                        'attempt': attempt + 1
                    }
                )

                # Mark provider success
                await provider_mgr.mark_provider_success(provider, channel, elapsed_ms)

                # Update user engagement (success)
                await orchestration_agent.update_user_engagement(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    channel=channel,
                    success=True,
                    delivery_time_seconds=int(elapsed_ms / 1000)
                )

                await db.commit()

                logger.info(f"{Fore.GREEN}✓ Notification {notification_id} sent via {provider}/{channel} in {elapsed_ms}ms (attempt {attempt + 1})")

                return {
                    'status': 'success',
                    'provider': provider,
                    'message_id': response.message_id,
                    'latency_ms': elapsed_ms,
                    'attempt': attempt + 1
                }

            else:
                # Provider returned failure
                raise Exception(
                    f"Provider returned failure: {response.error_code} - {response.error_message}"
                )

        except Exception as e:
            logger.warning(
                f"{Fore.RED}✗ Attempt {attempt + 1}/{max_attempts} failed for {provider}/{channel}: {e}"
            )

            # Log failure event
            await _log_event(
                db, notification_id, 'failed', channel, provider,
                {
                    'error': str(e),
                    'attempt': attempt + 1,
                    'latency_ms': int((time.time() - start_time) * 1000)
                }
            )

            # Mark provider failure
            await provider_mgr.mark_provider_failure(provider, channel)
            retryable_error = _is_retryable_channel_error(str(e))

            # Check if we should retry
            if attempt < max_attempts - 1 and retryable_error:
                # Get failover provider
                failover_provider = await provider_mgr.get_failover_provider(channel, provider)

                if failover_provider and failover_provider != provider:
                    logger.info(f"{Fore.YELLOW}→ Failing over to provider {failover_provider}")
                    provider = failover_provider

                # Exponential backoff
                delay = delays[min(attempt, len(delays) - 1)]
                logger.info(f"{Fore.CYAN}⏱ Retrying in {delay}s...")
                await asyncio.sleep(delay)

            else:
                # All retries exhausted
                channel_record.status = ChannelStatus.FAILED
                channel_record.error_message = str(e)
                channel_record.attempts = attempt + 1

                # Update notification if all channels failed
                notification.retry_count = attempt + 1

                # Log permanent failure
                await _log_event(
                    db, notification_id, 'permanently_failed', channel, provider,
                    {
                        'error': str(e),
                        'total_attempts': attempt + 1
                    }
                )

                # Update user engagement (failure)
                await orchestration_agent.update_user_engagement(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    channel=channel,
                    success=False
                )

                await db.commit()

                logger.error(
                    f"{Fore.RED}{Style.BRIGHT}✗ Notification {notification_id} permanently failed on {channel} "
                    f"after {attempt + 1} attempts"
                )
                if not retryable_error:
                    logger.error(
                        f"{Fore.RED}Non-retryable error for {provider}/{channel}; stopping retries: {e}"
                    )

                return {
                    'status': 'failed',
                    'provider': provider,
                    'error': str(e),
                    'attempts': attempt + 1
                }

    # Should never reach here
    return {'status': 'failed', 'error': 'Unknown error'}


async def _process_channels_sequential(
    db,
    notification: Notification,
    channel_records,
    provider_mgr: ProviderManager,
    orchestration_agent: OrchestrationAgent,
    max_attempts: int,
    channel_plan: list
) -> tuple[Dict[str, Any], bool]:
    """
    Process channels in strict sequential failover mode.
    Stops after first successful channel.
    """
    records_by_channel = {rec.channel: rec for rec in channel_records}
    ordered_records = []

    # Respect stored channel plan order first.
    for channel in channel_plan or []:
        rec = records_by_channel.get(channel)
        if rec and rec not in ordered_records:
            ordered_records.append(rec)

    # Append any records not listed in plan (safety fallback).
    for rec in channel_records:
        if rec not in ordered_records:
            ordered_records.append(rec)

    results: Dict[str, Any] = {}
    success_channel = None

    for channel_record in ordered_records:
        channel = channel_record.channel
        logger.info(f"{Fore.BLUE}[SEQUENTIAL] Processing channel {channel} for notification {notification.id}")
        result = await _send_via_channel(
            db=db,
            notification=notification,
            channel_record=channel_record,
            provider_mgr=provider_mgr,
            orchestration_agent=orchestration_agent,
            max_attempts=max_attempts
        )
        results[channel] = result

        if result.get('status') == 'success':
            success_channel = channel
            break

    if success_channel:
        skipped_msg = f"Skipped due to sequential failover success on channel '{success_channel}'"
        for rec in ordered_records:
            if rec.channel in results:
                continue
            rec.error_message = skipped_msg
            results[rec.channel] = {
                'status': 'skipped',
                'reason': skipped_msg,
                'attempts': rec.attempts or 0
            }

    return results, bool(success_channel)


async def _log_event(
    db,
    notification_id: UUID,
    event_type: str,
    channel: str,
    provider: str,
    metadata: Optional[Dict[str, Any]] = None
):
    """Log notification event to audit table."""
    try:
        query = text("""
            INSERT INTO notification_events
                (notification_id, event_type, channel, provider, metadata)
            VALUES
                (:notification_id, :event_type, :channel, :provider, CAST(:metadata AS jsonb))
        """)

        await db.execute(
            query,
            {
                'notification_id': str(notification_id),
                'event_type': event_type,
                'channel': channel,
                'provider': provider,
                'metadata': json.dumps(metadata or {})
            }
        )

    except Exception as e:
        logger.error(f"Failed to log event: {e}")


def _get_provider_instance(
    channel: str,
    provider: str,
    tenant_provider_config: Dict[str, Any] | None = None,
):
    """
    Get provider instance for channel.

    Maps channel + provider name to actual provider class instance.
    """
    from src.providers import get_provider_for_channel

    try:
        provider_instance = get_provider_for_channel(channel, provider, config=tenant_provider_config)

        if not provider_instance:
            logger.warning(f"Provider {provider} not available for channel {channel}")

        return provider_instance

    except Exception as e:
        logger.error(f"Failed to get provider instance: {e}")
        return None


async def _get_tenant_provider_config(
    db,
    tenant_id: str,
    channel: str,
) -> Dict[str, Any]:
    """Get active tenant provider config for a channel."""
    query = select(TenantProviderConfig).where(
        TenantProviderConfig.tenant_id == tenant_id,
        TenantProviderConfig.provider == channel,
        TenantProviderConfig.is_active == True,
    )
    result = await db.execute(query)
    row = result.scalar_one_or_none()
    return (row.config or {}) if row else {}


def _enforce_sender_identity(channel: str, provider_config: Dict[str, Any]) -> None:
    """Fail fast when tenant sender identity is missing."""
    required_sender_channels = {"email", "sms", "whatsapp", "voice"}
    if channel not in required_sender_channels:
        return
    sender = (
        provider_config.get("from_email")
        or provider_config.get("sender_email")
        or provider_config.get("from_number")
        or provider_config.get("sender_id")
    )
    if not sender:
        raise Exception(
            f"Tenant sender identity missing for channel '{channel}'. "
            "Configure tenant provider settings."
        )


def _build_message(notification: Notification, channel: str) -> Message:
    """
    Build Message object from notification data.

    Extracts recipient and content based on channel type.
    """
    data = notification.data or {}

    # Extract recipient based on channel
    recipient_map = {
        'email': data.get('email'),
        'sms': data.get('phone'),
        'whatsapp': data.get('phone'),
        'slack': data.get('slack_id'),
        'push': data.get('device_tokens', []),
        'voice': data.get('phone'),
    }

    recipient = recipient_map.get(channel, data.get('email', ''))

    # Handle push tokens (list)
    if isinstance(recipient, list):
        recipient = recipient[0] if recipient else ''

    message = Message(
        recipient=recipient,
        subject=data.get('subject'),
        body=data.get('body', ''),
        data=data,
        metadata={
            'notification_id': str(notification.id),
            'tenant_id': notification.tenant_id,
            'user_id': notification.user_id,
            'priority': notification.priority.value,
            'channel': channel
        }
    )

    return message

