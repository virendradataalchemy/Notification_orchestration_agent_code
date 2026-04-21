"""ChromaDB memory layer for agents."""
import chromadb
from chromadb.config import Settings
from typing import List, Dict, Any, Optional
import os
import logging

logger = logging.getLogger(__name__)


class AgentMemory:
    """
    Manages agent long-term memory using ChromaDB.

    Collections:
    - notification_decisions: Past notification decisions and outcomes
    - user_patterns: User behavior patterns
    """

    def __init__(self, persist_directory: str = None):
        if persist_directory is None:
            persist_directory = os.getenv("CHROMA_PERSIST_DIR", "./chroma_data")

        logger.info(f"Initializing ChromaDB at: {persist_directory}")

        self.client = chromadb.PersistentClient(
            path=persist_directory,
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=False
            )
        )

        # Create collections
        self.notifications_collection = self.client.get_or_create_collection(
            name="notification_decisions",
            metadata={
                "description": "Past notification decisions and outcomes",
                "hnsw:space": "cosine"  # Cosine similarity
            }
        )

        self.user_patterns_collection = self.client.get_or_create_collection(
            name="user_patterns",
            metadata={
                "description": "User behavior patterns",
                "hnsw:space": "cosine"
            }
        )

        logger.info(
            f"ChromaDB initialized: "
            f"{self.notifications_collection.count()} decisions, "
            f"{self.user_patterns_collection.count()} user patterns"
        )

    def store_decision(
        self,
        notification_id: str,
        decision_text: str,
        embedding: List[float],
        metadata: Dict[str, Any]
    ):
        """
        Store agent decision in memory.

        Args:
            notification_id: Unique notification identifier
            decision_text: Text description of decision
            embedding: Vector embedding of decision
            metadata: Additional metadata (user_id, channel, reward, etc)
        """
        try:
            self.notifications_collection.add(
                ids=[notification_id],
                documents=[decision_text],
                embeddings=[embedding],
                metadatas=[metadata]
            )
            logger.debug(f"Stored decision: {notification_id}")
        except Exception as e:
            logger.error(f"Failed to store decision: {e}")
            raise

    def retrieve_similar_decisions(
        self,
        query_embedding: List[float],
        n_results: int = 5,
        filter_metadata: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Retrieve similar past decisions using vector search.

        Args:
            query_embedding: Query vector
            n_results: Number of results to return
            filter_metadata: Optional metadata filters (e.g., {"user_id": "123"})

        Returns:
            Dictionary with ids, documents, distances, and metadatas
        """
        try:
            results = self.notifications_collection.query(
                query_embeddings=[query_embedding],
                n_results=n_results,
                where=filter_metadata
            )
            logger.debug(f"Retrieved {len(results['ids'][0]) if results['ids'] else 0} similar decisions")
            return results
        except Exception as e:
            logger.error(f"Failed to retrieve decisions: {e}")
            return {"ids": [[]], "documents": [[]], "distances": [[]], "metadatas": [[]]}

    def store_user_pattern(
        self,
        user_id: str,
        pattern_text: str,
        embedding: List[float],
        metadata: Dict[str, Any]
    ):
        """Store or update user behavior pattern."""
        try:
            self.user_patterns_collection.upsert(
                ids=[f"user_{user_id}"],
                documents=[pattern_text],
                embeddings=[embedding],
                metadatas=[metadata]
            )
            logger.debug(f"Stored user pattern: {user_id}")
        except Exception as e:
            logger.error(f"Failed to store user pattern: {e}")

    def get_user_patterns(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user behavior patterns."""
        try:
            result = self.user_patterns_collection.get(
                ids=[f"user_{user_id}"]
            )
            if result and result['ids']:
                return {
                    "pattern_text": result['documents'][0],
                    "metadata": result['metadatas'][0]
                }
            return None
        except Exception as e:
            logger.error(f"Failed to get user patterns: {e}")
            return None

    def get_stats(self) -> Dict[str, Any]:
        """Get memory statistics."""
        return {
            "decisions_count": self.notifications_collection.count(),
            "user_patterns_count": self.user_patterns_collection.count()
        }


# Singleton instance
_agent_memory = None


def get_agent_memory() -> AgentMemory:
    """Get singleton agent memory instance."""
    global _agent_memory
    if _agent_memory is None:
        _agent_memory = AgentMemory()
    return _agent_memory
