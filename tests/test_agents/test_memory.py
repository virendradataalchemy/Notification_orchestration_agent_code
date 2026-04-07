"""Tests for ChromaDB memory layer."""
import pytest
from src.agents.memory import AgentMemory


def test_chromadb_initialization():
    """Test ChromaDB memory initialization."""
    memory = AgentMemory()

    assert memory.client is not None
    assert memory.notifications_collection is not None
    assert memory.user_patterns_collection is not None

    stats = memory.get_stats()
    assert "decisions_count" in stats
    assert "user_patterns_count" in stats


def test_store_and_retrieve_decision():
    """Test storing and retrieving decisions."""
    memory = AgentMemory()

    # Store a test decision
    notification_id = "test_001"
    decision_text = "Test notification sent via email"
    embedding = [0.1] * 384  # Dummy embedding
    metadata = {
        "user_id": "test_user",
        "channel": "email",
        "reward": 3.5
    }

    memory.store_decision(
        notification_id=notification_id,
        decision_text=decision_text,
        embedding=embedding,
        metadata=metadata
    )

    # Retrieve similar
    similar = memory.retrieve_similar_decisions(
        query_embedding=embedding,
        n_results=1
    )

    assert similar is not None
    assert len(similar['ids'][0]) > 0
    assert notification_id in similar['ids'][0]


def test_cold_start_retrieval():
    """Test retrieval when ChromaDB is empty."""
    memory = AgentMemory()

    # Try to retrieve from empty collection
    similar = memory.retrieve_similar_decisions(
        query_embedding=[0.5] * 384,
        n_results=5,
        filter_metadata={"user_id": "nonexistent_user"}
    )

    # Should return empty results gracefully
    assert similar is not None
    assert "ids" in similar
