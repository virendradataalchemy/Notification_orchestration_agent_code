"""Main orchestration agent coordinating AI-powered notification routing."""

import logging
from typing import Dict, Any, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text

from .llm_service import BedrockLLMService
from .embedding_service import EmbeddingService
from .provider_manager import ProviderManager
from src.utils.deduplication import DeduplicationService
from src.core import get_redis_client
from src.models import UserPreference

logger = logging.getLogger(__name__)


class OrchestrationAgent:
    """
    Main agentic orchestration engine.

    Coordinates:
    1. Deduplication (idempotency, content hash, semantic)
    2. User context and engagement history
    3. Provider health monitoring
    4. LLM-based routing decisions
    5. Queue assignment by priority
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.llm = BedrockLLMService()
        self.embeddings = EmbeddingService()
        self.provider_mgr = ProviderManager(db)

    async def process_notification(
        self,
        tenant_id: str,
        user_id: str,
        notification_type: str,
        content: str,
        priority: str,
        requested_channels: list,
        metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Main orchestration pipeline.

        Returns:
            {
                'status': 'queued' | 'duplicate' | 'rejected',
                'reason': str,
                'llm_decision': dict,
                'notification_id': str (if duplicate),
                'provider_health': dict,
                'user_context': dict
            }
        """
        logger.info(
            f"Processing notification for user {user_id}, "
            f"type={notification_type}, priority={priority}"
        )

        # Step 1: Deduplication checks
        dedup_result = await self._check_deduplication(
            user_id, notification_type, content, metadata
        )

        if dedup_result['is_duplicate']:
            logger.info(f"Duplicate detected: {dedup_result['reason']}")
            return {
                'status': 'duplicate',
                'reason': dedup_result['reason'],
                'notification_id': dedup_result.get('existing_id')
            }

        # Step 2: Get user context (preferences + engagement history)
        user_context = await self._get_user_context(tenant_id, user_id)

        # Step 3: Get provider health status
        provider_health = await self.provider_mgr.get_provider_health_summary()

        # Step 4: LLM routing decision
        try:
            llm_decision = await self.llm.make_routing_decision(
                notification_content=content,
                user_context=user_context,
                provider_health=provider_health,
                priority=priority
            )

            logger.info(
                f"LLM decision: {llm_decision['channel']} via {llm_decision['timing']} "
                f"- {llm_decision['reasoning']}"
            )

        except Exception as e:
            logger.error(f"LLM decision failed: {e}, using fallback routing")
            llm_decision = self._fallback_routing(priority, requested_channels)

        # Step 5: Store content hash for future deduplication
        content_hash = self.embeddings.generate_content_hash(content)

        try:
            await self.embeddings.store_embedding(
                self.db, tenant_id, user_id, content, content_hash
            )
        except Exception as e:
            logger.error(f"Failed to store embedding: {e}")

        # Step 6: Mark as processed in Redis deduplication cache
        # We MUST do this here as well to ensure the notification is marked as processed
        # even if it wasn't caught in the analyzer
        await self._mark_as_processed(user_id, notification_type, content, metadata)

        return {
            'status': 'queued',
            'llm_decision': llm_decision,
            'provider_health': provider_health,
            'user_context': user_context
        }

    async def _check_deduplication(
        self,
        user_id: str,
        notification_type: str,
        content: str,
        metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Check for duplicate notifications.

        Checks:
        1. Idempotency key (if provided)
        2. Content hash (Redis cache)
        3. Semantic similarity (pgvector when available)
        """
        redis = await get_redis_client()
        dedup = DeduplicationService(redis, ttl=600)

        # Check 1: Idempotency key
        idempotency_key = metadata.get('idempotency_key')

        if idempotency_key:
            existing = await dedup.check_idempotency_key(idempotency_key)

            if existing:
                return {
                    'is_duplicate': True,
                    'reason': 'idempotency_key',
                    'existing_id': existing
                }

        # Check 2: Content hash (Redis)
        is_content_dup = await dedup.is_duplicate(user_id, notification_type, content)

        if is_content_dup:
            return {
                'is_duplicate': True,
                'reason': 'content_hash'
            }

        # Check 3: Semantic similarity (when pgvector available)
        try:
            semantic_dup = await self.embeddings.check_semantic_duplicate(
                self.db,
                tenant_id=metadata.get('tenant_id', ''),
                user_id=user_id,
                content=content,
                threshold=0.95
            )

            if semantic_dup:
                return {
                    'is_duplicate': True,
                    'reason': 'semantic_similarity',
                    'existing_id': semantic_dup
                }

        except Exception as e:
            logger.warning(f"Semantic dedup check failed: {e}")

        return {'is_duplicate': False, 'reason': None}

    async def _mark_as_processed(
        self,
        user_id: str,
        notification_type: str,
        content: str,
        metadata: Dict[str, Any]
    ):
        """Mark notification as processed in cache."""
        redis = await get_redis_client()
        dedup = DeduplicationService(redis, ttl=600)

        # Mark content as sent
        await dedup.mark_as_sent(user_id, notification_type, content)

        # Store idempotency key if provided
        idempotency_key = metadata.get('idempotency_key')

        if idempotency_key and metadata.get('notification_id'):
            await dedup.store_idempotency_key(
                idempotency_key,
                metadata['notification_id'],
                ttl=86400  # 24 hours
            )

    async def _get_user_context(self, tenant_id: str, user_id: str) -> Dict[str, Any]:
        """
        Get user preferences and engagement history.

        Returns context needed for LLM routing decision.
        """
        # Get user preferences
        query = select(UserPreference).where(
            UserPreference.tenant_id == tenant_id,
            UserPreference.user_id == user_id
        )

        result = await self.db.execute(query)
        prefs = result.scalar_one_or_none()

        # Get engagement statistics
        engagement_query = text("""
            SELECT
                channel,
                CASE
                    WHEN total_sent = 0 THEN 0.0
                    ELSE ROUND((success_count::numeric / total_sent), 2)
                END as success_rate,
                total_sent,
                avg_delivery_time_seconds,
                last_successful_delivery
            FROM user_engagement
            WHERE tenant_id = :tenant_id AND user_id = :user_id
            ORDER BY success_rate DESC
        """)

        engagement_result = await self.db.execute(
            engagement_query,
            {'tenant_id': tenant_id, 'user_id': user_id}
        )

        success_rates = {}
        engagement_stats = {}

        for row in engagement_result.fetchall():
            success_rates[row.channel] = float(row.success_rate)
            engagement_stats[row.channel] = {
                'success_rate': float(row.success_rate),
                'total_sent': row.total_sent,
                'avg_delivery_time': row.avg_delivery_time_seconds,
                'last_success': row.last_successful_delivery.isoformat() if row.last_successful_delivery else None
            }

        return {
            'preferred_channels': prefs.preferred_channels if prefs else {},
            'quiet_hours': prefs.quiet_hours if prefs else {},
            'timezone': prefs.timezone if prefs else 'UTC',
            'language': prefs.language if prefs else 'en',
            'success_rates': success_rates,
            'engagement_stats': engagement_stats,
            'current_time': datetime.utcnow().isoformat()
        }

    def _fallback_routing(
        self,
        priority: str,
        requested_channels: list
    ) -> Dict[str, Any]:
        """
        Fallback rule-based routing if LLM fails.

        Uses simple priority-based channel selection.
        """
        channel_map = {
            'critical': 'sms',
            'high': 'sms', # 'push',
            'medium': 'email',
            'low': 'email'
        }

        retry_map = {
            'critical': 'aggressive',
            'high': 'standard',
            'medium': 'standard',
            'low': 'relaxed'
        }

        # Use requested channel if available and priority is not critical
        if requested_channels and priority != 'critical':
            channel = requested_channels[0]
        else:
            channel = channel_map.get(priority, 'email')

        return {
            'channel': channel,
            'timing': 'immediate' if priority in ['critical', 'high'] else 'scheduled',
            'scheduled_time': None,
            'retry_strategy': retry_map.get(priority, 'standard'),
            'reasoning': f'Fallback rule-based routing for {priority} priority'
        }

    async def update_user_engagement(
        self,
        tenant_id: str,
        user_id: str,
        channel: str,
        success: bool,
        delivery_time_seconds: Optional[int] = None
    ):
        """
        Update user engagement statistics after delivery attempt.

        Called by workers after notification delivery.
        """
        try:
            if success:
                query = text("""
                    INSERT INTO user_engagement
                        (tenant_id, user_id, channel, success_count, failure_count,
                         total_sent, avg_delivery_time_seconds, last_successful_delivery)
                    VALUES
                        (:tenant_id, :user_id, :channel, 1, 0, 1,
                         :delivery_time, NOW())
                    ON CONFLICT (tenant_id, user_id, channel)
                    DO UPDATE SET
                        success_count = user_engagement.success_count + 1,
                        total_sent = user_engagement.total_sent + 1,
                        avg_delivery_time_seconds = (
                            COALESCE(user_engagement.avg_delivery_time_seconds, 0) + :delivery_time
                        ) / 2,
                        last_successful_delivery = NOW(),
                        updated_at = NOW()
                """)
            else:
                query = text("""
                    INSERT INTO user_engagement
                        (tenant_id, user_id, channel, success_count, failure_count, total_sent)
                    VALUES
                        (:tenant_id, :user_id, :channel, 0, 1, 1)
                    ON CONFLICT (tenant_id, user_id, channel)
                    DO UPDATE SET
                        failure_count = user_engagement.failure_count + 1,
                        total_sent = user_engagement.total_sent + 1,
                        updated_at = NOW()
                """)

            await self.db.execute(
                query,
                {
                    'tenant_id': tenant_id,
                    'user_id': user_id,
                    'channel': channel,
                    'delivery_time': delivery_time_seconds or 0
                }
            )

            await self.db.commit()

            logger.debug(
                f"Updated engagement for user {user_id}, channel {channel}, "
                f"success={success}"
            )

        except Exception as e:
            logger.error(f"Failed to update user engagement: {e}")
            await self.db.rollback()
