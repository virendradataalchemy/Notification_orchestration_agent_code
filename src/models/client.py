from __future__ import annotations

import hashlib
import secrets
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

    # API key columns
    api_key_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    api_key_prefix: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

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
        """SHA-256 hash of the API key — only this is stored in DB."""
        return hashlib.sha256(api_key.encode()).hexdigest()

    @staticmethod
    def generate_api_key(client_id: str, env: str = "live") -> tuple[str, str, str]:
        """
        Generate a secure API key.
        Returns: (full_key, hash, prefix)
        - full_key  → shown to client ONCE, never stored
        - hash      → stored in DB for validation
        - prefix    → stored in DB for display (e.g. sk_live_1_xxxx...)
        """
        random_part = secrets.token_urlsafe(32)
        prefix = f"sk_{env}_{client_id}"
        api_key = f"{prefix}_{random_part}"
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
