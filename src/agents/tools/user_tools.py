"""User analysis tools using ChromaDB."""
from strands.tools import tool
from typing import Dict, Any
from sqlalchemy import text, select
from src.core import get_redis_client
from src.core.database import AsyncSessionLocal
from src.utils.deduplication import DeduplicationService
from src.services.embedding_service import EmbeddingService
from src.agents.memory import get_agent_memory
import logging

logger = logging.getLogger(__name__)


@tool
async def check_for_duplicate(
    user_id: str,
    notification_type: str,
    content: str,
    idempotency_key: str = None
) -> Dict[str, Any]:
    """
    Check if notification is duplicate using ChromaDB.

    Checks:
    1. Idempotency key (Redis)
    2. Content hash (Redis)
    3. Semantic similarity (ChromaDB) - threshold 0.2

    Args:
        user_id: The user's ID
        notification_type: Type of notification
        content: Notification content
        idempotency_key: Optional idempotency key

    Returns:
        Dictionary with duplicate status, reason, and stop flag
    """
    redis = await get_redis_client()
    dedup = DeduplicationService(redis, ttl=600)

    # Check 1: Idempotency key
    if idempotency_key:
        existing = await dedup.check_idempotency_key(idempotency_key)
        if existing:
            return {
                "is_duplicate": True,
                "reason": "idempotency_key",
                "existing_id": existing,
                "stop": True
            }

    # Check 2: Content hash
    logger.info(f"Checking for content hash duplicate: user={user_id}, type={notification_type}")
    is_content_dup = await dedup.is_duplicate(user_id, notification_type, content)
    if is_content_dup:
        logger.info(f"Content hash duplicate detected for user={user_id}")
        return {
            "is_duplicate": True,
            "reason": "content_hash",
            "stop": True
        }

    # If it's not a duplicate, mark it as sent in cache to prevent future duplicates
    await dedup.mark_as_sent(user_id, notification_type, content)

    # Check 3: Semantic similarity using ChromaDB
    try:
        embeddings = EmbeddingService()
        embedding = embeddings.generate_embedding(content)

        memory = get_agent_memory()
        similar = memory.retrieve_similar_decisions(
            query_embedding=embedding,
            n_results=1,
            filter_metadata={"user_id": user_id}
        )

        # Cold start handling
        if not similar or not similar['ids'] or len(similar['ids'][0]) == 0:
            return {
                "is_duplicate": False,
                "reason": "cold_start",
                "note": "No past notifications in ChromaDB yet"
            }

        # Check similarity (0.2 threshold - more practical than 0.1)
        distance = similar['distances'][0][0]
        if distance < 0.2:
            return {
                "is_duplicate": True,
                "reason": "semantic_similarity_chromadb",
                "existing_id": similar['ids'][0][0],
                "similarity_score": 1 - distance,
                "stop": True
            }

    except Exception as e:
        logger.warning(f"ChromaDB semantic check failed: {e}")
        # Note: We don't stop processing here to allow graceful degradation
    
    return {"is_duplicate": False}


@tool
async def query_similar_past_notifications(
    user_id: str,
    content: str,
    n_results: int = 5
) -> Dict[str, Any]:
    """
    Query ChromaDB for similar past notifications.

    Uses vector similarity search to find relevant past decisions.

    Args:
        user_id: The user's ID
        content: Current notification content
        n_results: Number of similar results to return

    Returns:
        Dictionary with similar notifications and count
    """
    try:
        embeddings = EmbeddingService()
        embedding = embeddings.generate_embedding(content)

        memory = get_agent_memory()
        similar = memory.retrieve_similar_decisions(
            query_embedding=embedding,
            n_results=n_results,
            filter_metadata={"user_id": user_id}
        )

        # Cold start handling
        if not similar or not similar['ids'] or len(similar['ids'][0]) == 0:
            return {
                "similar_notifications": [],
                "count": 0,
                "note": "Cold start - ChromaDB empty. Using fallback."
            }

        results = []
        for i, notification_id in enumerate(similar['ids'][0]):
            results.append({
                "notification_id": notification_id,
                "similarity": 1 - similar['distances'][0][i],
                "metadata": similar['metadatas'][0][i],
                "decision_text": similar['documents'][0][i]
            })

        return {
            "similar_notifications": results,
            "count": len(results)
        }
    except Exception as e:
        logger.error(f"Failed to query similar notifications: {e}")
        return {
            "similar_notifications": [],
            "count": 0,
            "error": str(e)
        }


@tool
async def get_user_engagement_history(
    user_id: str,
    tenant_id: str = "default"
) -> Dict[str, Any]:
    """
    Get user's notification engagement statistics from database.

    Args:
        user_id: The user's ID
        tenant_id: The tenant's ID

    Returns:
        Dictionary with engagement metrics by channel
    """
    try:
        async with AsyncSessionLocal() as db:
            query = text("""
                SELECT
                    channel,
                    ROUND((success_count::numeric / NULLIF(total_sent, 0)), 2) as success_rate,
                    total_sent,
                    success_count,
                    failure_count,
                    avg_delivery_time_seconds,
                    last_successful_delivery
                FROM user_engagement
                WHERE tenant_id = :tenant_id AND user_id = :user_id
                ORDER BY success_rate DESC
            """)

            result = await db.execute(query, {
                "tenant_id": tenant_id,
                "user_id": user_id
            })
            rows = result.fetchall()

            engagement_data = {}
            for row in rows:
                engagement_data[row.channel] = {
                    "success_rate": float(row.success_rate or 0),
                    "total_sent": row.total_sent,
                    "success_count": row.success_count,
                    "failure_count": row.failure_count,
                    "avg_delivery_time": row.avg_delivery_time_seconds,
                    "last_success": row.last_successful_delivery.isoformat()
                        if row.last_successful_delivery else None
                }

            return engagement_data
    except Exception as e:
        logger.error(f"Failed to get user engagement history: {e}")
        return {}


@tool
async def get_user_preferences(
    user_id: str,
    tenant_id: str = "default"
) -> Dict[str, Any]:
    """
    Get user notification preferences from database.

    Args:
        user_id: The user's ID
        tenant_id: The tenant's ID

    Returns:
        User preferences including channels, quiet hours, timezone
    """
    try:
        async with AsyncSessionLocal() as db:
            from sqlalchemy import select
            from src.models import UserPreference

            query = select(UserPreference).where(
                UserPreference.tenant_id == tenant_id,
                UserPreference.user_id == user_id
            )

            result = await db.execute(query)
            prefs = result.scalar_one_or_none()

            if not prefs:
                return {
                    "preferred_channels": {},
                    "quiet_hours": {"start": "21:00", "end": "08:00"},
                    "timezone": "UTC",
                    "language": "en"
                }

            return {
                "preferred_channels": prefs.preferred_channels or {},
                "quiet_hours": prefs.quiet_hours or {},
                "timezone": prefs.timezone or "UTC",
                "language": prefs.language or "en"
            }
    except Exception as e:
        logger.error(f"Failed to get user preferences: {e}")
        return {
            "preferred_channels": {},
            "quiet_hours": {"start": "21:00", "end": "08:00"},
            "timezone": "UTC",
            "language": "en"
        }
