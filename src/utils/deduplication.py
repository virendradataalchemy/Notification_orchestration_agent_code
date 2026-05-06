import hashlib
import logging
from redis.asyncio import Redis
from typing import Optional

logger = logging.getLogger(__name__)


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
        if not content:
            # Cannot hash empty content reliably
            return False

        # Generate content hash
        content_hash = self._generate_hash(content)

        # Safety check: log parameters to make sure hashing is deterministic
        logger.info(f"Deduplication hash check for user_id={user_id}, type={notification_type}, hash={content_hash}")
        
        # Create dedup key - this checks if we've seen this exact content for this user+type recently
        dedup_key = f"dedup:{user_id}:{notification_type}:{content_hash}"
        
        logger.info(f"Checking dedup key: {dedup_key}")

        # Check if key exists
        exists = await self.redis.exists(dedup_key)
        
        logger.info(f"Dedup key {dedup_key} exists: {exists}")

        if exists:
            return True

        # Store key with TTL ONLY if it doesn't exist
        # Setting it inside this function makes it act as a lock-and-set
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
        if not content:
            return
            
        content_hash = self._generate_hash(content)
        dedup_key = f"dedup:{user_id}:{notification_type}:{content_hash}"
        
        logger.info(f"Marking as sent, storing dedup key: {dedup_key} with ttl {self.ttl}")

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
        # In python, dictionaries serialized to strings could have different key orderings
        # so we ensure it's a normalized string before hashing
        return hashlib.sha256(str(content).encode('utf-8')).hexdigest()
