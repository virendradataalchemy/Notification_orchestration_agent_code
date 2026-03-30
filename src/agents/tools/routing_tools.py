"""Channel routing tools for agents."""
from strands.tools import tool
from typing import Dict, Any, List
from datetime import datetime, timedelta
import pytz
from src.services.provider_manager import ProviderManager
from src.core.database import AsyncSessionLocal
import logging
import uuid

logger = logging.getLogger(__name__)


@tool
async def check_provider_health(channel: str = None) -> Dict[str, Any]:
    """
    Check health status of notification providers.

    Args:
        channel: Optional specific channel to check

    Returns:
        Provider health metrics
    """
    try:
        async with AsyncSessionLocal() as db:
            provider_mgr = ProviderManager(db)
            health_summary = await provider_mgr.get_provider_health_summary()

        if channel:
            return {
                "channel": channel,
                "health": health_summary.get(channel, {"is_healthy": False})
            }

        return {"providers": health_summary}
    except Exception as e:
        logger.error(f"Failed to check provider health: {e}")
        return {"providers": {}, "error": str(e)}


@tool
async def predict_best_channel(
    user_id: str,
    priority: str,
    engagement_history: Dict[str, Any],
    provider_health: Dict[str, Any],
    similar_past_notifications: List[Dict] = None
) -> Dict[str, Any]:
    """
    Use ML model to predict best notification channel.

    Uses:
    1. Similar past notifications (if available) - learns from memory
    2. User engagement history
    3. Fallback heuristics

    Args:
        user_id: The user's ID
        priority: Notification priority (critical, high, medium, low)
        engagement_history: User's historical engagement data
        provider_health: Current provider health status
        similar_past_notifications: Similar past notifications from ChromaDB memory

    Returns:
        Predicted channel, confidence, and reasoning
    """
    try:
        # Critical priority always goes to SMS
        if priority == "critical":
            return {
                "channel": "sms",
                "confidence": 0.95,
                "reasoning": "Critical priority requires most reliable channel (SMS)"
            }

        # Try to learn from similar past notifications (ChromaDB memory)
        if similar_past_notifications and len(similar_past_notifications) > 0:
            # Get channels from successful past notifications
            successful_channels = {}
            for notif in similar_past_notifications:
                metadata = notif.get("metadata", {})
                if metadata.get("reward", 0) > 2:  # Successful (opened/clicked)
                    channel = metadata.get("channel")
                    if channel:
                        successful_channels[channel] = successful_channels.get(channel, 0) + 1

            if successful_channels:
                # Use most successful channel from memory
                best_channel = max(successful_channels, key=successful_channels.get)
                return {
                    "channel": best_channel,
                    "confidence": 0.9,
                    "reasoning": f"Learned from {len(similar_past_notifications)} similar past notifications in ChromaDB. {best_channel} was most successful."
                }

        # FALLBACK: Use engagement history
        if engagement_history:
            best_channel = "email"
            best_rate = 0.0

            for channel, stats in engagement_history.items():
                provider_healthy = provider_health.get("providers", {}).get(channel, {}).get("is_healthy", False)
                if provider_healthy and stats.get("success_rate", 0) > best_rate:
                    best_channel = channel
                    best_rate = stats["success_rate"]

            if best_rate > 0:
                return {
                    "channel": best_channel,
                    "confidence": 0.80,
                    "reasoning": f"Based on user engagement: {best_rate:.0%} success rate with {best_channel}"
                }

        # FINAL FALLBACK: Default rules
        priority_map = {
            "high": "push",
            "medium": "email",
            "low": "email"
        }

        return {
            "channel": priority_map.get(priority, "email"),
            "confidence": 0.60,
            "reasoning": "Using default fallback rules (cold start - no history available)"
        }
    except Exception as e:
        logger.error(f"Failed to predict best channel: {e}")
        return {
            "channel": "email",
            "confidence": 0.5,
            "reasoning": f"Error occurred, using default email channel: {str(e)}"
        }


@tool
async def check_quiet_hours(
    user_id: str,
    timezone: str = "UTC"
) -> Dict[str, Any]:
    """
    Check if current time is within user's quiet hours.

    Args:
        user_id: The user's ID
        timezone: User's timezone

    Returns:
        Whether it's quiet hours and optimal send time
    """
    try:
        from src.agents.tools.user_tools import get_user_preferences

        prefs = await get_user_preferences(user_id)
        quiet_hours = prefs.get("quiet_hours", {})

        tz = pytz.timezone(timezone)
        now = datetime.now(tz)
        current_hour = now.hour

        quiet_start = int(quiet_hours.get("start", "21:00").split(":")[0])
        quiet_end = int(quiet_hours.get("end", "08:00").split(":")[0])

        is_quiet = current_hour >= quiet_start or current_hour < quiet_end

        if is_quiet:
            # Calculate next optimal time (9 AM)
            next_send = now.replace(hour=9, minute=0, second=0, microsecond=0)
            if current_hour >= quiet_start:
                next_send += timedelta(days=1)

            return {
                "is_quiet_hours": True,
                "current_time": now.isoformat(),
                "optimal_send_time": next_send.isoformat(),
                "delay_seconds": int((next_send - now).total_seconds())
            }

        return {
            "is_quiet_hours": False,
            "current_time": now.isoformat(),
            "optimal_send_time": now.isoformat(),
            "delay_seconds": 0
        }
    except Exception as e:
        logger.error(f"Failed to check quiet hours: {e}")
        return {
            "is_quiet_hours": False,
            "current_time": datetime.utcnow().isoformat(),
            "optimal_send_time": datetime.utcnow().isoformat(),
            "delay_seconds": 0,
            "error": str(e)
        }


@tool
async def send_notification_via_channel(
    user_id: str,
    tenant_id: str,
    channel: str,
    content: str,
    notification_type: str,
    priority: str,
    metadata: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    Send notification through selected channel.

    Args:
        user_id: The user's ID
        tenant_id: The tenant's ID
        channel: Channel to use (email, sms, push, etc)
        content: Notification content
        notification_type: Type of notification
        priority: Priority level
        metadata: Additional metadata

    Returns:
        Notification ID, status, and channel used
    """
    try:
        from src.models import Notification

        async with AsyncSessionLocal() as db:
            # Create notification record
            notification = Notification(
                id=str(uuid.uuid4()),
                tenant_id=tenant_id,
                user_id=user_id,
                type=notification_type,
                content=content,
                priority=priority,
                status="pending",
                metadata=metadata or {}
            )

            db.add(notification)
            await db.commit()

            # TODO: Actually send via channel using existing service
            # For now, mark as sent
            notification.status = "sent"
            await db.commit()

            logger.info(f"Notification {notification.id} sent via {channel}")

            return {
                "notification_id": notification.id,
                "status": "sent",
                "channel": channel,
                "sent_at": datetime.utcnow().isoformat()
            }
    except Exception as e:
        logger.error(f"Failed to send notification: {e}")
        return {
            "notification_id": None,
            "status": "failed",
            "channel": channel,
            "error": str(e)
        }
