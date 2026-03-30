from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Dict, Any
from datetime import datetime, time
import pytz

from src.models import UserPreference


class MessageRouter:
    """Intelligent message routing based on priority and user preferences."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def select_channels(
        self,
        user_id: str,
        notification_type: str,
        priority: str,
        requested_channels: List[str],
    ) -> List[str]:
        """
        Select appropriate channels for notification delivery.

        Args:
            user_id: User identifier
            notification_type: Type of notification
            priority: Priority level (critical, high, medium, low)
            requested_channels: Channels requested by sender

        Returns:
            List of selected channel names
        """
        # Get user preferences
        query = select(UserPreference).where(UserPreference.user_id == user_id)
        result = await self.db.execute(query)
        preferences = result.scalar_one_or_none()

        # Check if user has opted out
        if preferences and preferences.unsubscribed:
            if notification_type in preferences.unsubscribed:
                return []  # User opted out of this notification type

        # Priority-based routing
        if priority == "critical":
            # CRITICAL: Immediate delivery via fastest channels
            return ["sms", "push", "voice"]

        elif priority == "high":
            # HIGH: Within 1 minute via preferred channel with fallback
            if preferences and preferences.preferred_channels:
                user_channels = preferences.preferred_channels.get(
                    notification_type, requested_channels
                )
                # Check quiet hours
                if self._is_quiet_hours(preferences):
                    # Still send high priority, but via less intrusive channels
                    return ["email", "inapp"]
                return user_channels
            return requested_channels

        elif priority == "medium":
            # MEDIUM: Within 5 minutes, optimize for cost
            if preferences and preferences.preferred_channels:
                return preferences.preferred_channels.get(
                    notification_type, requested_channels
                )
            return requested_channels

        else:  # low
            # LOW: Within 1 hour, batch for cost efficiency
            if self._is_quiet_hours(preferences):
                # Schedule for later
                return []
            return requested_channels if requested_channels else ["email"]

    def _is_quiet_hours(self, preferences: UserPreference) -> bool:
        """
        Check if current time is within user's quiet hours.

        Args:
            preferences: User preferences with quiet hours settings

        Returns:
            True if currently in quiet hours
        """
        if not preferences or not preferences.quiet_hours:
            return False

        try:
            timezone = pytz.timezone(preferences.timezone or "UTC")
            current_time = datetime.now(timezone).time()

            quiet_start = datetime.strptime(
                preferences.quiet_hours.get("start", "22:00"), "%H:%M"
            ).time()
            quiet_end = datetime.strptime(
                preferences.quiet_hours.get("end", "08:00"), "%H:%M"
            ).time()

            if quiet_start < quiet_end:
                return quiet_start <= current_time <= quiet_end
            else:
                # Quiet hours span midnight
                return current_time >= quiet_start or current_time <= quiet_end

        except Exception:
            return False

    async def get_channel_failover(
        self, primary_channel: str, notification_type: str
    ) -> List[str]:
        """
        Get failover channels if primary channel fails.

        Args:
            primary_channel: The channel that failed
            notification_type: Type of notification

        Returns:
            List of failover channels to try
        """
        failover_map = {
            "email": ["push", "inapp"],
            "sms": ["whatsapp", "push"],
            "whatsapp": ["sms", "push"],
            "push": ["email", "inapp"],
            "slack": ["email"],
            "voice": ["sms", "push"],
        }

        return failover_map.get(primary_channel, ["email"])
