"""Embedding service for content deduplication using ChromaDB."""

import asyncio
import hashlib
import logging
import json
from typing import Optional, List
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import chromadb

logger = logging.getLogger(__name__)


class EmbeddingService:
    """
    Service for generating embeddings and detecting duplicate content.

    Uses ChromaDB as vector database (works on Windows without PostgreSQL extensions).
    """

    def __init__(self, persist_directory: str = "./chroma_data"):
        self.use_semantic = True
        self.model = None
        self.persist_directory = persist_directory
        self.chroma_client = None
        self.collection = None

    def _init_chromadb(self):
        """Initialize ChromaDB client and collection."""
        if self.chroma_client is None:
            try:
                # ChromaDB 1.5+ uses PersistentClient
                self.chroma_client = chromadb.PersistentClient(
                    path=self.persist_directory
                )

                # Create or get collection for notification embeddings
                self.collection = self.chroma_client.get_or_create_collection(
                    name="notification_embeddings",
                    metadata={"description": "Notification content embeddings for deduplication"}
                )

                logger.info(f"ChromaDB initialized at {self.persist_directory}")
            except Exception as e:
                logger.error(f"Failed to initialize ChromaDB: {e}")
                self.use_semantic = False

    def _init_model(self):
        """Lazy load the sentence transformer model."""
        if self.model is None and self.use_semantic:
            try:
                from sentence_transformers import SentenceTransformer
                # Using all-MiniLM-L6-v2: fast, 384 dimensions, good quality
                self.model = SentenceTransformer('all-MiniLM-L6-v2')
                logger.info("Sentence transformer model loaded (all-MiniLM-L6-v2, 384 dims)")
            except Exception as e:
                logger.warning(f"Could not load sentence transformer: {e}")
                self.use_semantic = False

    def generate_embedding(self, content: str) -> Optional[List[float]]:
        """
        Generate embedding vector for text content.

        Returns None if semantic search is not available.
        """
        if not self.use_semantic:
            return None

        self._init_model()

        if self.model is None:
            return None

        try:
            return self.model.encode(content).tolist()
        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            return None

    def generate_content_hash(self, content: str) -> str:
        """Generate SHA-256 hash of content for exact deduplication."""
        return hashlib.sha256(content.encode()).hexdigest()

    async def check_semantic_duplicate(
        self,
        db: AsyncSession,
        client_id: str,
        user_id: str,
        content: str,
        threshold: float = 0.95
    ) -> Optional[str]:
        """
        Check if semantically similar notification was sent recently.

        Uses ChromaDB for vector similarity search.

        Returns notification embedding id if duplicate found, None otherwise.
        """
        content_hash = self.generate_content_hash(content)

        # Step 1: Check by content hash in PostgreSQL (exact match - fastest)
        query = text("""
            SELECT id
            FROM notification_embeddings
            WHERE client_id = :client_id
              AND user_id = :user_id
              AND content_hash = :content_hash
              AND created_at > NOW() - INTERVAL '10 minutes'
            LIMIT 1
        """)

        result = await db.execute(
            query,
            {
                'client_id': client_id,
                'user_id': user_id,
                'content_hash': content_hash
            }
        )

        row = result.fetchone()

        if row:
            logger.info(f"Exact duplicate found for user {user_id}")
            return str(row.id)

        # Step 2: Semantic similarity check using ChromaDB
        if not self.use_semantic:
            return None

        # Initialize ChromaDB if needed
        self._init_chromadb()

        if self.collection is None:
            logger.warning("ChromaDB not available, skipping semantic check")
            return None

        # Generate embedding for current content (run in thread to avoid blocking)
        try:
            embedding = await asyncio.to_thread(self.generate_embedding, content)
        except RuntimeError as e:
            # Handle "Event loop is closed" error gracefully
            logger.warning(f"Could not generate embedding (event loop issue): {e}")
            return None

        if not embedding:
            return None

        try:
            # # Calculate time threshold (10 minutes ago)
            # ten_minutes_ago = (datetime.utcnow() - timedelta(minutes=10)).isoformat()

            # # Query ChromaDB for similar embeddings (run in thread to avoid blocking)
            # results = await asyncio.to_thread(
            #     self.collection.query,
            #     query_embeddings=[embedding],
            #     n_results=1,
            #     where={
            #         "$and": [
            #             {"client_id": client_id},
            #             {"user_id": user_id},
            #             {"created_at": {"$gte": ten_minutes_ago}}
            #         ]
            #     }
            # )

            # Use Unix timestamp (float) instead of .isoformat()
            ten_minutes_ago_timestamp = (datetime.utcnow() - timedelta(minutes=10)).timestamp()

            # Query ChromaDB for similar embeddings
            results = await asyncio.to_thread(
                self.collection.query,
                query_embeddings=[embedding],
                n_results=1,
                where={
                    "$and": [
                        {"client_id": client_id},
                        {"user_id": user_id},
                        # Use the float timestamp for comparison
                        {"created_at": {"$gte": ten_minutes_ago_timestamp}}
                    ]
                }
            )

            # Check if we found a match above threshold
            if results['ids'][0] and results['distances'][0]:
                # ChromaDB returns L2 distance, convert to cosine similarity
                # similarity = 1 - (distance / 2)  # For normalized vectors
                distance = results['distances'][0][0]

                # For cosine similarity with normalized vectors:
                # similarity = 1 - distance (if using cosine distance)
                # ChromaDB uses L2 by default, so we approximate:
                similarity = 1 - (distance / 2)

                if similarity >= threshold:
                    doc_id = results['ids'][0][0]
                    logger.info(
                        f"Semantic duplicate found (ChromaDB): "
                        f"similarity={similarity:.3f} for user {user_id}"
                    )
                    return doc_id

        except Exception as e:
            logger.error(f"ChromaDB similarity search failed: {e}")

        return None

    async def store_embedding(
        self,
        db: AsyncSession,
        client_id: str,
        user_id: str,
        content: str,
        content_hash: str
    ):
        """
        Store content hash in PostgreSQL and embedding in ChromaDB.
        """
        try:
            # Generate embedding if semantic search is enabled (run in thread)
            embedding = None
            if self.use_semantic:
                try:
                    embedding = await asyncio.to_thread(self.generate_embedding, content)
                except RuntimeError as e:
                    logger.warning(f"Could not generate embedding (event loop issue): {e}")
                    embedding = None

            # Store metadata in PostgreSQL for exact hash matching
            query = text("""
                INSERT INTO notification_embeddings
                    (client_id, user_id, content_hash, notification_content)
                VALUES
                    (:client_id, :user_id, :content_hash, :content)
                RETURNING id
            """)

            result = await db.execute(
                query,
                {
                    'client_id': client_id,
                    'user_id': user_id,
                    'content_hash': content_hash,
                    'content': content[:500]  # Store truncated content
                }
            )

            row = result.fetchone()
            embedding_id = str(row.id) if row else None

            await db.commit()

            # Store embedding in ChromaDB if available (run in thread)
            if embedding and embedding_id:
                self._init_chromadb()

                if self.collection is not None:
                    try:
                        await asyncio.to_thread(
                            self.collection.add,
                            embeddings=[embedding],
                            documents=[content[:500]],
                            ids=[embedding_id],
                            metadatas=[{
                                "client_id": client_id,
                                "user_id": user_id,
                                "content_hash": content_hash,
                                # "created_at": datetime.utcnow().isoformat()
                                # Store as Unix timestamp (float)
                                "created_at": datetime.utcnow().timestamp()
                            }]
                        )
                        logger.debug(f"Stored embedding (ChromaDB) for user {user_id}")
                    except RuntimeError as e:
                        logger.warning(f"Could not store embedding in ChromaDB (event loop issue): {e}")
            else:
                logger.debug(f"Stored content hash only for user {user_id}")

        except Exception as e:
            logger.error(f"Failed to store embedding: {e}")
            await db.rollback()

    async def cleanup_old_embeddings(self, db: AsyncSession):
        """
        Cleanup old embeddings from PostgreSQL.
        ChromaDB cleanup done separately via cleanup_chromadb().
        """
        try:
            # Clean PostgreSQL
            query = text("""
                DELETE FROM notification_embeddings
                WHERE created_at < NOW() - INTERVAL '10 minutes'
            """)

            result = await db.execute(query)
            await db.commit()

            deleted_count = result.rowcount
            if deleted_count > 0:
                logger.info(f"Cleaned up {deleted_count} old embeddings from PostgreSQL")

        except Exception as e:
            logger.error(f"Failed to cleanup PostgreSQL embeddings: {e}")
            await db.rollback()

    def cleanup_chromadb(self):
        """
        Cleanup old embeddings from ChromaDB (older than 10 minutes).
        Call this periodically (e.g., via scheduled task).
        """
        try:
            self._init_chromadb()

            if self.collection is None:
                return

            # # Calculate time threshold
            # ten_minutes_ago = (datetime.utcnow() - timedelta(minutes=10)).isoformat()

            # # Get all old documents
            # results = self.collection.get(
            #     where={"created_at": {"$lt": ten_minutes_ago}},
            #     limit=10000  # Process in batches
            # )

            # if results['ids']:
            #     self.collection.delete(ids=results['ids'])
            #     logger.info(f"Cleaned up {len(results['ids'])} old embeddings from ChromaDB")

            # Calculate float timestamp threshold
            ten_minutes_ago_timestamp = (datetime.utcnow() - timedelta(minutes=10)).timestamp()

            # Get all old documents using numeric comparison
            results = self.collection.get(
                where={"created_at": {"$lt": ten_minutes_ago_timestamp}},
                limit=10000 
            )

            if results['ids']:
                self.collection.delete(ids=results['ids'])
                logger.info(f"Cleaned up {len(results['ids'])} old embeddings from ChromaDB")

        except Exception as e:
            logger.error(f"Failed to cleanup ChromaDB embeddings: {e}")
