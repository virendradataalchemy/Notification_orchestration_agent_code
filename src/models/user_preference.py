from __future__ import annotations

from typing import Optional

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class UserPreference(Base):
    __tablename__ = "client_preferences"

    user_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    client_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("clients.id"), nullable=True, index=True)
    preferred_channels: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    quiet_hours: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    unsubscribed: Mapped[Optional[list[str]]] = mapped_column(ARRAY(String), nullable=True)
    language: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    timezone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
