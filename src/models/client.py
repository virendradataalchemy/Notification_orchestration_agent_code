from __future__ import annotations

import hashlib
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Client(Base):
    """Client mapped to the live Supabase clients table."""

    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    default_language: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    logo_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    brand_color: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    client_slug: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    supabase_uid: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    created_at: Mapped[Optional[DateTime]] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[Optional[DateTime]] = mapped_column(DateTime, nullable=True)

    candidates = relationship("Candidate", back_populates="client")
    templates = relationship("Template", back_populates="client")
    communications = relationship("Communication", back_populates="client")

    @property
    def status(self) -> str:
        return "active" if self.is_active else "inactive"

    @property
    def config(self) -> dict:
        return {}

    @property
    def deleted_at(self):
        return None

    @staticmethod
    def hash_api_key(api_key: str) -> str:
        return hashlib.sha256(api_key.encode()).hexdigest()

    @staticmethod
    def generate_api_key(client_id: str, env: str = "live") -> tuple[str, str, str]:
        prefix = f"sk_{env}_{client_id}"
        api_key = f"{prefix}_unsupported"
        return api_key, Client.hash_api_key(api_key), prefix


class ClientProviderConfig(Base):
    """
    Compatibility model for older endpoints.

    The live schema uses the `providers` table; this table may not exist in Supabase.
    It remains mapped only so old imports do not fail.
    """

    __tablename__ = "client_provider_configs"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    client_id: Mapped[str] = mapped_column(String(50), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
