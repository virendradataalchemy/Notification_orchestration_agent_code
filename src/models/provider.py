from __future__ import annotations

from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Provider(Base):
    __tablename__ = "providers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[Optional[int]] = mapped_column(ForeignKey("tenants.id"), nullable=True, index=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    config_ref: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[Optional[DateTime]] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[Optional[DateTime]] = mapped_column(DateTime, nullable=True)

    channel = relationship("Channel", back_populates="providers")
    attempts = relationship("CommunicationAttempt", back_populates="provider")
