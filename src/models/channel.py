from __future__ import annotations

from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Channel(Base):
    __tablename__ = "channels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[Optional[DateTime]] = mapped_column(DateTime, nullable=True)

    providers = relationship("Provider", back_populates="channel")
    templates = relationship("Template", back_populates="channel_ref")
    communications = relationship("Communication", back_populates="channel_ref")
    events = relationship("NotificationEvent", back_populates="channel_ref")
