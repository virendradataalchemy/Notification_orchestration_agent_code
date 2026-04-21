from __future__ import annotations

from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Template(Base):
    __tablename__ = "templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"), nullable=False, index=True)
    language: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    subject: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    variable_schema: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notification_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    department: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    visibility: Mapped[str] = mapped_column(String(20), nullable=False, default="public", server_default="public", index=True)
    created_at: Mapped[Optional[DateTime]] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[Optional[DateTime]] = mapped_column(DateTime, nullable=True)

    client = relationship("Client", back_populates="templates")
    channel_ref = relationship("Channel", back_populates="templates")
    communications = relationship("Communication", back_populates="template")
    departments = relationship("TemplateDepartment", back_populates="template", cascade="all, delete-orphan")

    @property
    def active(self) -> bool:
        return self.is_active

    @active.setter
    def active(self, value: bool) -> None:
        self.is_active = value

    @property
    def body(self) -> str:
        return self.content

    @body.setter
    def body(self, value: str) -> None:
        self.content = value

    @property
    def channel(self) -> Optional[str]:
        return self.channel_ref.name if self.channel_ref else None

    @property
    def is_global(self) -> bool:
        return self.client_id is None

    @property
    def base_template_id(self) -> Optional[int]:
        return None


class TemplateDepartment(Base):
    __tablename__ = "template_departments"
    __table_args__ = (UniqueConstraint("template_id", "department", name="uq_template_departments_template_department"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    template_id: Mapped[int] = mapped_column(ForeignKey("templates.id", ondelete="CASCADE"), nullable=False, index=True)
    department: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    created_at: Mapped[Optional[DateTime]] = mapped_column(DateTime, nullable=True)

    template = relationship("Template", back_populates="departments")
