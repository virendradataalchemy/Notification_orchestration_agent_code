"""Provider health tracking and failover management."""

import logging
from typing import Optional, Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class ProviderManager:
    """
    Manages provider health tracking and intelligent failover.

    Implements circuit breaker pattern for provider failures.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.providers = {
            'email': ['mailgun', 'aws_ses', 'azure_graph'],  # Mailgun is now primary
            'sms': ['twilio', 'aws_sns'],
            'push': ['fcm', 'apns'],
            'slack': ['slack_api'],
            'whatsapp': ['twilio'],
            'voice': ['twilio'],
            'inapp': ['websocket'],
        }

        # Circuit breaker thresholds
        self.failure_threshold = 5  # Mark unhealthy after 5 consecutive failures
        self.recovery_time = 300  # Try recovery after 5 minutes

    async def get_healthy_provider(self, channel: str) -> str:
        """
        Get the healthiest provider for a channel.

        Returns the provider with the best health score.
        Falls back to first available if no health data exists.
        """
        available_providers = self.providers.get(channel, [])

        if not available_providers:
            logger.warning(f"No providers configured for channel: {channel}")
            return 'unknown'

        try:
            # Query provider health with health score calculation
            query = text("""
                SELECT
                    provider_name,
                    CASE
                        WHEN total_sent = 0 THEN 0.5
                        ELSE success_count::float / total_sent
                    END as health_score,
                    is_healthy,
                    last_check
                FROM (
                    SELECT
                        provider_name,
                        success_count,
                        failure_count,
                        (success_count + failure_count) as total_sent,
                        is_healthy,
                        last_check
                    FROM provider_health
                    WHERE channel = :channel
                      AND provider_name = ANY(:providers)
                ) subquery
                ORDER BY is_healthy DESC, health_score DESC, last_check DESC
                LIMIT 1
            """)

            result = await self.db.execute(
                query,
                {'channel': channel, 'providers': available_providers}
            )

            row = result.fetchone()

            if row:
                # Check if unhealthy provider should be retried (circuit breaker recovery)
                if not row.is_healthy:
                    time_since_check = datetime.utcnow() - row.last_check
                    if time_since_check.total_seconds() >= self.recovery_time:
                        logger.info(f"Attempting recovery for provider {row.provider_name}")
                        await self._reset_provider_health(row.provider_name, channel)
                        return row.provider_name

                if row.is_healthy:
                    return row.provider_name

        except Exception as e:
            logger.error(f"Error querying provider health: {e}")

        # Return first available provider if no health data or all unhealthy
        logger.info(f"Using default provider {available_providers[0]} for channel {channel}")
        return available_providers[0]

    async def mark_provider_success(
        self,
        provider: str,
        channel: str,
        latency_ms: int
    ):
        """
        Record successful delivery.

        Updates success counter and marks provider as healthy.
        """
        try:
            query = text("""
                INSERT INTO provider_health
                    (provider_name, channel, success_count, failure_count, avg_latency_ms, is_healthy, last_check)
                VALUES
                    (:provider, :channel, 1, 0, :latency, TRUE, NOW())
                ON CONFLICT (provider_name, channel)
                DO UPDATE SET
                    success_count = provider_health.success_count + 1,
                    avg_latency_ms = (
                        COALESCE(provider_health.avg_latency_ms, 0) + :latency
                    ) / 2,
                    is_healthy = TRUE,
                    last_check = NOW()
            """)

            await self.db.execute(
                query,
                {
                    'provider': provider,
                    'channel': channel,
                    'latency': latency_ms
                }
            )

            await self.db.commit()

            logger.debug(f"Recorded success for provider {provider} on channel {channel}")

        except Exception as e:
            logger.error(f"Failed to mark provider success: {e}")
            await self.db.rollback()

    async def mark_provider_failure(self, provider: str, channel: str):
        """
        Record failed delivery and implement circuit breaker.

        Marks provider as unhealthy after threshold failures.
        """
        try:
            query = text("""
                INSERT INTO provider_health
                    (provider_name, channel, success_count, failure_count, is_healthy, last_check)
                VALUES
                    (:provider, :channel, 0, 1, TRUE, NOW())
                ON CONFLICT (provider_name, channel)
                DO UPDATE SET
                    failure_count = provider_health.failure_count + 1,
                    is_healthy = CASE
                        WHEN provider_health.failure_count + 1 >= :threshold THEN FALSE
                        ELSE TRUE
                    END,
                    last_check = NOW()
                RETURNING is_healthy
            """)

            result = await self.db.execute(
                query,
                {
                    'provider': provider,
                    'channel': channel,
                    'threshold': self.failure_threshold
                }
            )

            row = result.fetchone()
            await self.db.commit()

            if row and not row.is_healthy:
                logger.warning(
                    f"Provider {provider} marked UNHEALTHY for channel {channel} "
                    f"after {self.failure_threshold} failures"
                )
            else:
                logger.debug(f"Recorded failure for provider {provider} on channel {channel}")

        except Exception as e:
            logger.error(f"Failed to mark provider failure: {e}")
            await self.db.rollback()

    async def get_failover_provider(
        self,
        channel: str,
        failed_provider: str
    ) -> Optional[str]:
        """
        Get next available healthy provider for failover.

        Excludes the failed provider and returns the healthiest alternative.
        """
        available = self.providers.get(channel, [])

        # Remove failed provider
        remaining = [p for p in available if p != failed_provider]

        if not remaining:
            logger.error(f"No failover providers available for channel {channel}")
            return None

        try:
            # Get healthiest remaining provider
            query = text("""
                SELECT provider_name
                FROM provider_health
                WHERE channel = :channel
                  AND provider_name = ANY(:providers)
                  AND is_healthy = TRUE
                ORDER BY
                    success_count::float / NULLIF(success_count + failure_count, 0) DESC
                LIMIT 1
            """)

            result = await self.db.execute(
                query,
                {'channel': channel, 'providers': remaining}
            )

            row = result.fetchone()

            if row:
                logger.info(f"Failover to provider {row.provider_name} for channel {channel}")
                return row.provider_name

        except Exception as e:
            logger.error(f"Error finding failover provider: {e}")

        # Return first remaining if no health data
        logger.info(f"Using fallback provider {remaining[0]} for channel {channel}")
        return remaining[0]

    async def get_provider_health_summary(self) -> Dict[str, str]:
        """
        Get current health summary of all providers.

        Returns dict mapping channel to healthy provider name.
        """
        try:
            query = text("""
                SELECT DISTINCT ON (channel)
                    channel,
                    provider_name
                FROM provider_health
                WHERE is_healthy = TRUE
                ORDER BY channel, last_check DESC
            """)

            result = await self.db.execute(query)

            health_summary = {row.channel: row.provider_name for row in result.fetchall()}

            return health_summary

        except Exception as e:
            logger.error(f"Failed to get health summary: {e}")
            return {}

    async def _reset_provider_health(self, provider: str, channel: str):
        """Reset provider health for circuit breaker recovery attempt."""
        try:
            query = text("""
                UPDATE provider_health
                SET is_healthy = TRUE,
                    failure_count = 0,
                    last_check = NOW()
                WHERE provider_name = :provider
                  AND channel = :channel
            """)

            await self.db.execute(query, {'provider': provider, 'channel': channel})
            await self.db.commit()

            logger.info(f"Reset health for provider {provider} on channel {channel}")

        except Exception as e:
            logger.error(f"Failed to reset provider health: {e}")
            await self.db.rollback()

    async def get_provider_stats(self, channel: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get detailed statistics for all providers.

        Useful for monitoring and analytics.
        """
        try:
            if channel:
                where_clause = "WHERE channel = :channel"
                params = {'channel': channel}
            else:
                where_clause = ""
                params = {}

            query = text(f"""
                SELECT
                    provider_name,
                    channel,
                    success_count,
                    failure_count,
                    (success_count + failure_count) as total_sent,
                    CASE
                        WHEN (success_count + failure_count) = 0 THEN 0
                        ELSE ROUND((success_count::float / (success_count + failure_count) * 100), 2)
                    END as success_rate,
                    avg_latency_ms,
                    is_healthy,
                    last_check
                FROM provider_health
                {where_clause}
                ORDER BY channel, success_rate DESC
            """)

            result = await self.db.execute(query, params)

            stats = [
                {
                    'provider': row.provider_name,
                    'channel': row.channel,
                    'success_count': row.success_count,
                    'failure_count': row.failure_count,
                    'total_sent': row.total_sent,
                    'success_rate': float(row.success_rate),
                    'avg_latency_ms': row.avg_latency_ms,
                    'is_healthy': row.is_healthy,
                    'last_check': row.last_check.isoformat() if row.last_check else None
                }
                for row in result.fetchall()
            ]

            return stats

        except Exception as e:
            logger.error(f"Failed to get provider stats: {e}")
            return []
