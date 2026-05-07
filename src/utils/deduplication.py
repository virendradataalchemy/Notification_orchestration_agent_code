import hashlib
from redis.asyncio import Redis
from typing import Optional


class DeduplicationService:
    """Service for detecting and preventing duplicate notifications."""

    def __init__(self, redis: Redis, ttl: int = 600):
        """
        Initialize deduplication service.

        Args:
            redis: Redis client
            ttl: Time-to-live for dedup keys in seconds (default: 10 minutes)
        """
        self.redis = redis
        self.ttl = ttl

    async def is_duplicate(
        self,
        user_id: str,
        notification_type: str,
        content: str
    ) -> bool:
        """
        Check if notification is a duplicate.

        Args:
            user_id: User identifier
            notification_type: Type of notification
            content: Notification content

        Returns:
            True if duplicate, False otherwise
        """
        # Generate content hash
        content_hash = self._generate_hash(content)

        # Create dedup key
        dedup_key = f"dedup:{user_id}:{notification_type}:{content_hash}"

        # Check if key exists
        exists = await self.redis.exists(dedup_key)

        if exists:
            return True

        # Store key with TTL
        await self.redis.setex(dedup_key, self.ttl, "1")

        return False

    async def mark_as_sent(
        self,
        user_id: str,
        notification_type: str,
        content: str
    ):
        """
        Mark notification as sent (for deduplication).

        Args:
            user_id: User identifier
            notification_type: Type of notification
            content: Notification content
        """
        content_hash = self._generate_hash(content)
        dedup_key = f"dedup:{user_id}:{notification_type}:{content_hash}"

        await self.redis.setex(dedup_key, self.ttl, "1")

    async def check_idempotency_key(
        self,
        idempotency_key: str
    ) -> Optional[str]:
        """
        Check if idempotency key was already processed.

        Args:
            idempotency_key: Client-provided idempotency key

        Returns:
            Notification ID if already processed, None otherwise
        """
        key = f"idempotency:{idempotency_key}"
        notification_id = await self.redis.get(key)

        return notification_id

    async def store_idempotency_key(
        self,
        idempotency_key: str,
        notification_id: str,
        ttl: int = 86400  # 24 hours
    ):
        """
        Store idempotency key with notification ID.

        Args:
            idempotency_key: Client-provided idempotency key
            notification_id: Notification ID that was created
            ttl: Time-to-live in seconds (default: 24 hours)
        """
        key = f"idempotency:{idempotency_key}"
        await self.redis.setex(key, ttl, notification_id)

    def _generate_hash(self, content: str) -> str:
        """
        Generate SHA-256 hash of content.

        Args:
            content: Content to hash

        Returns:
            Hexadecimal hash string
        """
        return hashlib.sha256(content.encode()).hexdigest()
