from sqlalchemy import Column, String, Integer, DateTime, Boolean, UniqueConstraint
from datetime import datetime
from .base import Base

class ProviderHealth(Base):
    """Tracks global health and success rates for each provider/channel combination."""

    __tablename__ = "provider_health"

    id = Column(Integer, primary_key=True, autoincrement=True)
    provider_name = Column(String(100), nullable=False)
    channel = Column(String(50), nullable=False, index=True)
    
    success_count = Column(Integer, nullable=False, default=0)
    failure_count = Column(Integer, nullable=False, default=0)
    avg_latency_ms = Column(Integer, nullable=True)
    is_healthy = Column(Boolean, nullable=False, default=True, index=True)
    last_check = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('provider_name', 'channel', name='uq_provider_channel'),
    )

    def __repr__(self):
        return f"<ProviderHealth(provider={self.provider_name}, channel={self.channel}, healthy={self.is_healthy})>"
