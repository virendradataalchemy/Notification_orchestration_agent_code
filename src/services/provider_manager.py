"""Provider selection against the live Supabase providers table."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Channel, Provider

logger = logging.getLogger(__name__)


class ProviderManager:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_healthy_provider(self, channel: str, client_id: Optional[int] = None) -> str:
        provider = await self._get_provider(channel, client_id)
        return provider.name if provider else "unknown"

    async def mark_provider_success(self, provider: str, channel: str, latency_ms: int):
        logger.debug("Provider success recorded for %s/%s (%sms)", provider, channel, latency_ms)

    async def mark_provider_failure(self, provider: str, channel: str):
        logger.warning("Provider failure recorded for %s/%s", provider, channel)

    async def get_failover_provider(
        self, channel: str, failed_provider: str, client_id: Optional[int] = None
    ) -> Optional[str]:
        providers = await self._list_providers(channel, client_id)
        for provider in providers:
            if provider.name != failed_provider:
                return provider.name
        return None

    async def get_provider_id(self, provider_name: str, channel: str) -> Optional[int]:
        """Get provider DB id by name and channel."""
        result = await self.db.execute(
            select(Provider)
            .join(Channel, Provider.channel_id == Channel.id)
            .where(Provider.name == provider_name, Channel.name == channel)
        )
        provider = result.scalars().first()
        return provider.id if provider else None

    async def get_provider_health_summary(self) -> Dict[str, str]:
        result = await self.db.execute(
            select(Channel, Provider)
            .join(Provider, Provider.channel_id == Channel.id)
            .where(Channel.is_active == True, Provider.is_active == True)
            .order_by(Channel.name.asc(), Provider.priority.asc())
        )

        summary: Dict[str, str] = {}
        for channel, provider in result.all():
            summary.setdefault(channel.name, provider.name)
        return summary

    async def get_provider_stats(self, channel: Optional[str] = None) -> List[Dict[str, Any]]:
        query = (
            select(Channel, Provider)
            .join(Provider, Provider.channel_id == Channel.id)
            .where(Channel.is_active == True, Provider.is_active == True)
            .order_by(Channel.name.asc(), Provider.priority.asc())
        )
        if channel:
            query = query.where(Channel.name == channel)

        result = await self.db.execute(query)
        return [
            {
                "provider": provider.name,
                "channel": channel_row.name,
                "success_count": None,
                "failure_count": None,
                "total_sent": None,
                "success_rate": None,
                "avg_latency_ms": None,
                "is_healthy": True,
                "last_check": None,
            }
            for channel_row, provider in result.all()
        ]

    async def _get_provider(self, channel: str, client_id: Optional[int]) -> Optional[Provider]:
        providers = await self._list_providers(channel, client_id)
        return providers[0] if providers else None

    async def _list_providers(self, channel: str, client_id: Optional[int]) -> List[Provider]:
        query = (
            select(Provider)
            .join(Channel, Provider.channel_id == Channel.id)
            .where(Channel.name == channel, Channel.is_active == True, Provider.is_active == True)
            .order_by(Provider.client_id.desc(), Provider.priority.asc(), Provider.id.asc())
        )
        if client_id is not None:
            query = query.where((Provider.client_id == client_id) | (Provider.client_id.is_(None)))

        result = await self.db.execute(query)
        return list(result.scalars().all())
