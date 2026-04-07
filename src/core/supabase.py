from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from src.config import settings


logger = logging.getLogger(__name__)

CLIENTS_TABLE = "clients"
CANDIDATES_TABLE = "candidates"
COMMUNICATIONS_TABLE = "communications"
CLIENT_PREFERENCES_TABLE = "client_preferences"


class SupabaseClient:
    """Minimal Supabase REST client using URL + API key."""

    def __init__(self):
        self.base_url = (settings.supabase_url or "").rstrip("/")
        self.api_key = settings.supabase_service_role_key or settings.supabase_key

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.api_key)

    def _headers(self) -> dict[str, str]:
        return {
            "apikey": self.api_key,
            "Authorization": f"Bearer {self.api_key}",
        }

    async def select(
        self,
        table: str,
        select_expr: str = "*",
        *,
        limit: Optional[int] = None,
        filters: Optional[dict[str, str]] = None,
    ) -> list[dict[str, Any]]:
        if not self.configured:
            raise RuntimeError("Supabase REST client is not configured")

        params: dict[str, Any] = {"select": select_expr}
        if limit is not None:
            params["limit"] = limit
        if filters:
            params.update(filters)

        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(
                f"{self.base_url}/rest/v1/{table}",
                headers=self._headers(),
                params=params,
            )
            response.raise_for_status()
            return response.json()

    async def insert(
        self,
        table: str,
        payload: dict[str, Any] | list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not self.configured:
            raise RuntimeError("Supabase REST client is not configured")

        headers = self._headers()
        headers["Prefer"] = "return=representation"

        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                f"{self.base_url}/rest/v1/{table}",
                headers=headers,
                json=payload,
            )
            if response.is_error:
                recovered = await self._retry_insert_on_primary_key_conflict(
                    client=client,
                    table=table,
                    headers=headers,
                    payload=payload,
                    response=response,
                )
                if recovered is not None:
                    return recovered
                logger.error(
                    "Supabase insert failed for table '%s' with status %s: %s",
                    table,
                    response.status_code,
                    response.text,
                )
                response.raise_for_status()
            return response.json()

    async def update(
        self,
        table: str,
        payload: dict[str, Any],
        *,
        filters: Optional[dict[str, str]] = None,
    ) -> list[dict[str, Any]]:
        if not self.configured:
            raise RuntimeError("Supabase REST client is not configured")

        headers = self._headers()
        headers["Prefer"] = "return=representation"

        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.patch(
                f"{self.base_url}/rest/v1/{table}",
                headers=headers,
                params=filters or {},
                json=payload,
            )
            response.raise_for_status()
            return response.json()

    async def upsert(
        self,
        table: str,
        payload: dict[str, Any] | list[dict[str, Any]],
        *,
        on_conflict: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Insert or update a row. Uses PostgREST upsert via Prefer header."""
        if not self.configured:
            raise RuntimeError("Supabase REST client is not configured")

        headers = self._headers()
        headers["Prefer"] = "return=representation,resolution=merge-duplicates"
        headers["Content-Type"] = "application/json"

        params = {}
        if on_conflict:
            params["on_conflict"] = on_conflict

        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                f"{self.base_url}/rest/v1/{table}",
                headers=headers,
                params=params,
                json=payload,
            )
            response.raise_for_status()
            return response.json()

    async def health_check(self) -> dict[str, Any]:
        rows = await self.select(CLIENTS_TABLE, "id,name", limit=1)
        return {
            "configured": self.configured,
            "reachable": True,
            "sample_rows": len(rows),
        }

    async def _retry_insert_on_primary_key_conflict(
        self,
        *,
        client: httpx.AsyncClient,
        table: str,
        headers: dict[str, str],
        payload: dict[str, Any] | list[dict[str, Any]],
        response: httpx.Response,
    ) -> Optional[list[dict[str, Any]]]:
        if response.status_code != 409:
            return None

        detail = response.text.lower()
        if "duplicate key value violates unique constraint" not in detail:
            return None
        if "_pkey" not in detail and "key (id)=" not in detail:
            return None

        rows = payload if isinstance(payload, list) else [payload]
        if not rows or any("id" in row for row in rows):
            return None

        latest_rows = await self.select(
            table,
            "id",
            limit=1,
            filters={"order": "id.desc"},
        )
        next_id = int(latest_rows[0]["id"]) + 1 if latest_rows else 1

        retry_payload = []
        for offset, row in enumerate(rows):
            retry_row = dict(row)
            retry_row["id"] = next_id + offset
            retry_payload.append(retry_row)

        logger.warning(
            "Retrying Supabase insert for table '%s' with explicit ids starting at %s after primary key conflict.",
            table,
            next_id,
        )
        retry_response = await client.post(
            f"{self.base_url}/rest/v1/{table}",
            headers=headers,
            json=retry_payload if isinstance(payload, list) else retry_payload[0],
        )
        if retry_response.is_error:
            logger.error(
                "Supabase retry insert failed for table '%s' with status %s: %s",
                table,
                retry_response.status_code,
                retry_response.text,
            )
            retry_response.raise_for_status()
        return retry_response.json()


supabase_client = SupabaseClient()
