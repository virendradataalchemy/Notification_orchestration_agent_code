from sqlalchemy import Column, String, Text, DateTime, Integer
from sqlalchemy.dialects.postgresql import TIMESTAMP
from datetime import datetime
from .base import Base

class NotificationEmbedding(Base):
    """Stores notification content hashes for deduplication."""

    __tablename__ = "notification_embeddings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(50), nullable=False, index=True)
    user_id = Column(String(50), nullable=False, index=True)
    content_hash = Column(String(64), nullable=False, index=True)
    notification_content = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)

    __table_args__ = (
        # Note: Index on (tenant_id, user_id) is also common
    )

    def __repr__(self):
        return f"<NotificationEmbedding(user_id={self.user_id}, hash={self.content_hash})>"
