from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from typing import Any, Optional

import httpx
from jinja2 import Environment, StrictUndefined

from src.config import settings
from src.core import get_redis_client, supabase_client
from src.providers import get_provider_for_channel
from src.providers.base import Message, ProviderStatus
from src.utils.deduplication import DeduplicationService

logger = logging.getLogger(__name__)


class SupabaseNotificationService:
    def __init__(self):
        self.template_env = Environment(undefined=StrictUndefined, autoescape=False)

    async def get_demo_options(self, client_id: int) -> dict[str, Any]:
        data = await self._load_reference_data(client_id)
        channels_by_id = {row["id"]: row["name"] for row in data["channels"]}
        return {
            "client": data["client"],
            "candidates": data["candidates"],
            "channels": data["channels"],
            "providers": data["providers"],
            "templates": [
                {
                    **template,
                    "channel": channels_by_id.get(template.get("channel_id"), "unknown"),
                }
                for template in data["templates"]
            ],
        }

    async def send_notification(self, client_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        data = await self._load_reference_data(client_id)
        client = data["client"]
        candidate = self._resolve_candidate(payload, data["candidates"])
        if not candidate:
            raise ValueError("No matching candidate found for this client")

        # Normalize channel names: "inapp" → "in_app"
        if payload.get("channels"):
            payload["channels"] = [
                "in_app" if ch == "inapp" else ch
                for ch in payload["channels"]
            ]

        selected_channels = self._select_channels(payload, data["channels"], data["templates"])
        if not selected_channels:
            raise ValueError("No deliverable channels available")

        requested_data = payload.get("data") or {}
        template_id = payload.get("template_id")
        notification_type = payload.get("notification_type") or payload.get("type") or "demo_notification"
        raw_priority = str(payload.get("priority") or "medium").lower()
        # Strip enum prefix if present e.g. "priority.medium" → "medium"
        priority = raw_priority.split(".")[-1] if "." in raw_priority else raw_priority
        base_idempotency_key = payload.get("idempotency_key")

        duplicate_info = await self._check_duplicate(
            client_id=client_id,
            candidate_id=candidate["id"],
            notification_type=notification_type,
            payload_data=requested_data,
            idempotency_key=base_idempotency_key,
        )
        if duplicate_info:
            duplicate_info["deduplicated"] = True
            return duplicate_info

        results = []
        for channel_name in selected_channels:
            channel = next((row for row in data["channels"] if row["name"] == channel_name), None)
            if not channel:
                continue

            template = self._resolve_template(
                template_id=template_id,
                notification_type=notification_type,
                channel_id=channel["id"],
                templates=data["templates"],
            )
            provider = self._resolve_provider(channel["id"], data["providers"])

            render_context = {
                **requested_data,
                "name": candidate.get("name") or "",
                "email": candidate.get("email") or "",
                "phone": candidate.get("phone") or "",
                "whatsapp_number": candidate.get("whatsapp_number") or "",
                "company": candidate.get("company") or client.get("name") or "",
            }
            rendered_subject, rendered_body = self._render_message(payload, template, render_context)

            # Fallback: agar body empty hai toh notification_type use karo
            if not rendered_body:
                rendered_body = f"Notification: {notification_type}"
            
            # For push notifications, try to get device token from database
            if channel_name == "push":
                recipient = await self._resolve_push_recipient(candidate, payload)
            else:
                recipient = self._resolve_recipient(channel_name, candidate, payload)
            
            communication_idempotency_key = (
                f"{base_idempotency_key}:{channel_name}" if base_idempotency_key else None
            )

            try:
                # Fetch the latest id for communications
                latest_comms = await supabase_client.select(
                    "communications",
                    "id",
                    limit=1,
                    filters={"order": "id.desc"},
                )
                next_comm_id = int(latest_comms[0]["id"]) + 1 if latest_comms else 1
                
                communication_rows = await supabase_client.insert(
                    "communications",
                    {
                        "id": next_comm_id,
                        "client_id": client_id,
                        "candidate_id": candidate["id"],
                        "triggered_by_user_id": None,
                        "batch_id": None,
                        "notification_type": notification_type,
                        "channel_id": channel["id"],
                        "priority": priority,
                        "template_id": template.get("id") if template else None,
                        "status": "queued",
                        "idempotency_key": communication_idempotency_key,
                        "scheduled_at": None,
                        "sent_at": None,
                        "retry_count": 0,
                        "max_retries": int(settings.retry_max_attempts),
                    },
                )
                communication = communication_rows[0]
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code != 409 or not communication_idempotency_key:
                    raise
                existing = await self._find_existing_by_idempotency(
                    client_id=client_id,
                    idempotency_key=communication_idempotency_key,
                )
                if existing:
                    results.append(
                        {
                            "communication_id": existing["id"],
                            "channel": channel_name,
                            "provider": provider.get("name") if provider else "unknown",
                            "status": str(existing.get("status", "queued")).lower(),
                            "message_id": None,
                            "error": "Duplicate channel request skipped",
                        }
                    )
                    continue
                raise

            await self._store_payload(
                communication_id=communication["id"],
                payload={
                    **{k: self._stringify(v) for k, v in render_context.items()},
                    "subject": rendered_subject,
                    "body": rendered_body,
                    "recipient": recipient,
                    "channel": channel_name,
                    "provider_name": provider.get("name") if provider else None,
                    "template_id": template.get("id") if template else None,
                },
            )
            await self._append_event(
                communication_id=communication["id"],
                event_type="queued",
                channel_id=channel["id"],
                status="queued",
                metadata={"provider": provider.get("name") if provider else None},
            )

            provider_result = await self._deliver(
                communication_id=communication["id"],
                candidate=candidate,
                channel_name=channel_name,
                provider=provider,
                rendered_subject=rendered_subject,
                rendered_body=rendered_body,
                recipient=recipient,
                channel_id=channel["id"],
                priority=priority,
            )
            results.append(provider_result)

        return {
            "client_id": client_id,
            "client_name": client.get("name"),
            "candidate_id": candidate["id"],
            "candidate_name": candidate.get("name"),
            "notification_type": notification_type,
            "priority": priority,
            "channels": results,
            "deduplicated": False,
        }

    async def get_history(self, client_id: int, limit: int = 20) -> list[dict[str, Any]]:
        data = await self._load_reference_data(client_id, include_runtime=True)
        channels_by_id = {row["id"]: row["name"] for row in data["channels"]}
        templates_by_id = {row["id"]: row for row in data["templates"]}
        candidates_by_id = {row["id"]: row for row in data["candidates"]}
        attempts_by_comm: dict[int, list[dict[str, Any]]] = {}
        for attempt in data["attempts"]:
            attempts_by_comm.setdefault(attempt.get("communication_id"), []).append(attempt)

        history = []
        for communication in sorted(data["communications"], key=lambda row: row.get("created_at") or "", reverse=True)[:limit]:
            template = templates_by_id.get(communication.get("template_id"))
            candidate = candidates_by_id.get(communication.get("candidate_id"), {})
            attempts = attempts_by_comm.get(communication["id"], [])
            history.append(
                {
                    "id": communication["id"],
                    "candidate_name": candidate.get("name"),
                    "recipient": candidate.get("email") or candidate.get("phone") or candidate.get("whatsapp_number") or candidate.get("id"),
                    "type": communication.get("notification_type"),
                    "priority": str(communication.get("priority", "medium")).lower(),
                    "status": str(communication.get("status", "unknown")).lower(),
                    "channel": channels_by_id.get(communication.get("channel_id"), "unknown"),
                    "template_name": template.get("name") if template else None,
                    "attempts": max((int(a.get("attempt_number") or 0) for a in attempts), default=0),
                    "last_error": next((a.get("error_message") for a in reversed(attempts) if a.get("error_message")), None),
                    "created_at": communication.get("created_at"),
                    "sent_at": communication.get("sent_at"),
                }
            )
        return history

    async def get_notification_status(self, client_id: int, communication_id: int) -> dict[str, Any]:
        data = await self._load_reference_data(client_id, include_runtime=True)
        communication = next((row for row in data["communications"] if row["id"] == communication_id), None)
        if not communication:
            raise ValueError("Notification not found")

        attempts = [row for row in data["attempts"] if row.get("communication_id") == communication_id]
        events = [row for row in data["events"] if row.get("communication_id") == communication_id]
        channels_by_id = {row["id"]: row["name"] for row in data["channels"]}
        candidates_by_id = {row["id"]: row for row in data["candidates"]}

        return {
            "id": communication["id"],
            "client_id": communication.get("client_id"),
            "candidate": candidates_by_id.get(communication.get("candidate_id")),
            "type": communication.get("notification_type"),
            "priority": str(communication.get("priority", "medium")).lower(),
            "status": str(communication.get("status", "unknown")).lower(),
            "channel": channels_by_id.get(communication.get("channel_id"), "unknown"),
            "attempts": attempts,
            "events": events,
            "created_at": communication.get("created_at"),
            "sent_at": communication.get("sent_at"),
        }

    async def _load_reference_data(self, client_id: int, include_runtime: bool = False) -> dict[str, Any]:
        clients = await supabase_client.select("clients", "id,name,is_active,created_at", filters={"id": f"eq.{client_id}"}, limit=1)
        if not clients:
            raise ValueError("Client not found")

        data = {
            "client": clients[0],
            "candidates": await supabase_client.select("candidates", "id,client_id,name,email,phone,whatsapp_number,company,language,metadata", filters={"client_id": f"eq.{client_id}"}),
            "channels": await supabase_client.select("channels", "id,name,priority,is_active", filters={"is_active": "eq.true"}),
            "providers": await supabase_client.select("providers", "id,client_id,channel_id,name,priority,is_active", filters={"is_active": "eq.true"}),
            "templates": await supabase_client.select("templates", "id,client_id,name,language,subject,content,version,is_active,notification_type,channel_id,created_at", filters={"client_id": f"eq.{client_id}", "is_active": "eq.true"}),
        }
        if include_runtime:
            data["communications"] = await supabase_client.select(
                "communications",
                "id,client_id,candidate_id,notification_type,channel_id,priority,status,template_id,idempotency_key,created_at,sent_at,retry_count",
                filters={"client_id": f"eq.{client_id}", "order": "created_at.desc"},
            )
            data["attempts"] = await supabase_client.select("communication_attempts", "id,communication_id,attempt_number,status,error_message,error_code,provider_id,created_at")
            data["events"] = await supabase_client.select("notification_events", "id,communication_id,event_type,channel_id,status,metadata,created_at")
        return data

    def _resolve_candidate(self, payload: dict[str, Any], candidates: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
        candidate_id = payload.get("candidate_id")
        if candidate_id is not None:
            return next((row for row in candidates if row["id"] == int(candidate_id)), None)
        email = payload.get("email")
        phone = payload.get("phone")
        if email:
            match = next((row for row in candidates if row.get("email") == email), None)
            if match:
                return match
        if phone:
            return next((row for row in candidates if row.get("phone") == phone or row.get("whatsapp_number") == phone), None)
        return None

    def _select_channels(self, payload: dict[str, Any], channels: list[dict[str, Any]], templates: list[dict[str, Any]]) -> list[str]:
        active_names = [row["name"] for row in sorted(channels, key=lambda item: item.get("priority", 999)) if row.get("is_active", True)]
        requested = payload.get("channels") or []
        if requested:
            return [channel for channel in requested if channel in active_names]

        template_id = payload.get("template_id")
        if template_id:
            try:
                tid = int(template_id)
                template = next((row for row in templates if row["id"] == tid), None)
            except (ValueError, TypeError):
                template = None
            if template:
                channel_name = next((row["name"] for row in channels if row["id"] == template.get("channel_id")), None)
                return [channel_name] if channel_name else []

        priority = str(payload.get("priority") or "medium").lower()
        if priority == "critical":
            preferred = ["sms", "voice", "push"]
            return [channel for channel in preferred if channel in active_names]

        notification_type = str(payload.get("notification_type") or payload.get("type") or "").lower()
        if notification_type in {"marketing"} and "email" in active_names:
            return ["email"]
        if notification_type in {"transactional", "confirmation", "invitation", "interview", "payslip"}:
            return [channel for channel in ["email", "push"] if channel in active_names] or active_names[:1]

        return ["email"] if "email" in active_names else active_names[:1]

    def _resolve_template(
        self,
        *,
        template_id: Any,
        notification_type: str,
        channel_id: int,
        templates: list[dict[str, Any]],
    ) -> Optional[dict[str, Any]]:
        # Lookup by ID — guard against non-numeric or mismatched IDs
        if template_id is not None:
            try:
                tid = int(template_id)
                template = next((row for row in templates if row["id"] == tid), None)
                if template:
                    return template
                # ID provided but not found — log and fall through to type-based lookup
                logger.warning(
                    "Template id=%s not found in client templates, falling back to type/channel lookup",
                    template_id,
                )
            except (ValueError, TypeError):
                logger.warning(
                    "Non-numeric template_id=%r, falling back to type/channel lookup",
                    template_id,
                )

        # Exact match: channel + notification_type
        exact = next(
            (
                row for row in templates
                if row.get("channel_id") == channel_id
                and row.get("notification_type") == notification_type
                and row.get("is_active", True)
            ),
            None,
        )
        if exact:
            return exact

        # Fallback 1: any active template for this channel
        channel_match = next(
            (row for row in templates if row.get("channel_id") == channel_id and row.get("is_active", True)),
            None,
        )
        if channel_match:
            return channel_match

        # Fallback 2: notification_type match on any channel (e.g. voice template stored under different channel)
        type_match = next(
            (
                row for row in templates
                if row.get("notification_type") == notification_type
                and row.get("is_active", True)
            ),
            None,
        )
        return type_match

    def _resolve_provider(self, channel_id: int, providers: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
        candidates = [row for row in providers if row.get("channel_id") == channel_id and row.get("is_active", True)]
        candidates.sort(key=lambda item: (item.get("client_id") is None, item.get("priority", 999), item.get("id", 999999)))
        return candidates[0] if candidates else None

    def _render_message(self, payload: dict[str, Any], template: Optional[dict[str, Any]], render_context: dict[str, Any]) -> tuple[str, str]:
        subject = payload.get("subject") or (template or {}).get("subject") or ""
        body = payload.get("body") or (template or {}).get("content") or ""
        rendered_subject = self._render_string(subject, render_context) if subject else ""
        rendered_body = self._render_string(body, render_context) if body else ""
        return rendered_subject, rendered_body

    def _render_string(self, value: str, context: dict[str, Any]) -> str:
        try:
            return self.template_env.from_string(value).render(**context)
        except Exception:
            return value

    async def _check_duplicate(
        self,
        *,
        client_id: int,
        candidate_id: int,
        notification_type: str,
        payload_data: dict[str, Any],
        idempotency_key: Optional[str],
    ) -> Optional[dict[str, Any]]:
        if idempotency_key:
            rows = await supabase_client.select(
                "communications",
                "id,client_id,candidate_id,notification_type,status,channel_id,created_at",
                limit=1,
                filters={
                    "client_id": f"eq.{client_id}",
                    "idempotency_key": f"eq.{idempotency_key}",
                    "order": "created_at.desc",
                },
            )
            if rows:
                return {
                    "status": "duplicate",
                    "message": "Request skipped because the idempotency key already exists",
                    "existing_communication_id": rows[0]["id"],
                }

        try:
            redis = await get_redis_client()
            dedup = DeduplicationService(redis, ttl=settings.dedup_ttl_seconds)
            content = json.dumps(payload_data, sort_keys=True)
            is_duplicate = await dedup.is_duplicate(str(candidate_id), notification_type, content)
            if is_duplicate:
                return {
                    "status": "duplicate",
                    "message": "Request skipped because a recent duplicate was detected",
                    "existing_communication_id": None,
                }
        except Exception:
            return None
        return None

    async def _find_existing_by_idempotency(self, *, client_id: int, idempotency_key: str) -> Optional[dict[str, Any]]:
        rows = await supabase_client.select(
            "communications",
            "id,client_id,candidate_id,notification_type,status,channel_id,created_at",
            limit=1,
            filters={
                "client_id": f"eq.{client_id}",
                "idempotency_key": f"eq.{idempotency_key}",
                "order": "created_at.desc",
            },
        )
        return rows[0] if rows else None

    async def _store_payload(self, communication_id: int, payload: dict[str, Any]) -> None:
        rows = [{"communication_id": communication_id, "key": key, "value": self._stringify(value)} for key, value in payload.items()]
        if rows:
            # Fetch the latest id to generate sequential ids for the batch
            latest_rows = await supabase_client.select(
                "communication_payloads",
                "id",
                limit=1,
                filters={"order": "id.desc"},
            )
            next_id = int(latest_rows[0]["id"]) + 1 if latest_rows else 1
            
            # Assign sequential ids to each row
            for offset, row in enumerate(rows):
                row["id"] = next_id + offset
            
            await supabase_client.insert("communication_payloads", rows)

    async def _append_event(
        self,
        *,
        communication_id: int,
        event_type: str,
        channel_id: Optional[int],
        status: Optional[str],
        metadata: dict[str, Any],
    ) -> None:
        # Fetch the latest id to generate the next id
        latest_rows = await supabase_client.select(
            "notification_events",
            "id",
            limit=1,
            filters={"order": "id.desc"},
        )
        next_id = int(latest_rows[0]["id"]) + 1 if latest_rows else 1
        
        await supabase_client.insert(
            "notification_events",
            {
                "id": next_id,
                "communication_id": communication_id,
                "event_type": event_type,
                "channel_id": channel_id,
                "status": status,
                "metadata": metadata,
            },
        )

    async def _deliver(
        self,
        *,
        communication_id: int,
        candidate: dict[str, Any],
        channel_name: str,
        provider: Optional[dict[str, Any]],
        rendered_subject: str,
        rendered_body: str,
        recipient: str,
        channel_id: int,
        priority: str,
    ) -> dict[str, Any]:
        provider_name = provider.get("name") if provider else None
        normalized_provider = self._normalize_provider_name(provider_name)
        provider_instance = get_provider_for_channel(channel_name, normalized_provider)
        if provider_instance is None:
            await self._record_failure(
                communication_id=communication_id,
                channel_id=channel_id,
                provider_id=provider.get("id") if provider else None,
                error_message="Provider not configured",
            )
            return {
                "communication_id": communication_id,
                "channel": channel_name,
                "provider": provider_name or "unconfigured",
                "status": "failed",
                "message_id": None,
                "error": "Provider not configured",
            }

        if not recipient:
            error_message = self._missing_recipient_error(channel_name)
            await self._record_failure(
                communication_id=communication_id,
                channel_id=channel_id,
                provider_id=provider.get("id") if provider else None,
                error_message=error_message,
                error_code="MISSING_RECIPIENT",
            )
            return {
                "communication_id": communication_id,
                "channel": channel_name,
                "provider": provider_name or normalized_provider or "unknown",
                "status": "failed",
                "message_id": None,
                "error": error_message,
            }

        try:
            response = await provider_instance.send(
                Message(
                    recipient=recipient,
                    subject=rendered_subject or None,
                    body=rendered_body,
                    data={"body": rendered_body, "subject": rendered_subject, "candidate_name": candidate.get("name")},
                    metadata={
                        "notification_id": str(communication_id),
                        "priority": priority,
                        "channel": channel_name,
                        "candidate_id": candidate.get("id"),
                        "client_id": candidate.get("client_id"),
                    },
                )
            )
        except Exception as exc:
            await self._record_failure(
                communication_id=communication_id,
                channel_id=channel_id,
                provider_id=provider.get("id") if provider else None,
                error_message=str(exc),
            )
            return {
                "communication_id": communication_id,
                "channel": channel_name,
                "provider": provider_name or normalized_provider or "unknown",
                "status": "failed",
                "message_id": None,
                "error": str(exc),
            }

        if response.status == ProviderStatus.SUCCESS:
            final_status = "delivered" if channel_name in {"in_app", "slack"} else "sent"
            await supabase_client.update(
                "communications",
                {
                    "status": final_status,
                    "sent_at": datetime.utcnow().isoformat(),
                    "updated_at": datetime.utcnow().isoformat(),
                },
                filters={"id": f"eq.{communication_id}"},
            )
            
            # Fetch the latest id for communication_attempts
            latest_attempts = await supabase_client.select(
                "communication_attempts",
                "id",
                limit=1,
                filters={"order": "id.desc"},
            )
            next_attempt_id = int(latest_attempts[0]["id"]) + 1 if latest_attempts else 1
            
            await supabase_client.insert(
                "communication_attempts",
                {
                    "id": next_attempt_id,
                    "communication_id": communication_id,
                    "attempt_number": 1,
                    "provider_id": provider.get("id") if provider else None,
                    "status": final_status,
                    "error_message": None,
                    "error_code": None,
                },
            )
            await self._append_event(
                communication_id=communication_id,
                event_type=final_status,
                channel_id=channel_id,
                status=final_status,
                metadata={"provider": provider_name or normalized_provider, "message_id": response.message_id, **(response.metadata or {})},
            )
            return {
                "communication_id": communication_id,
                "channel": channel_name,
                "provider": provider_name or normalized_provider or "default",
                "status": final_status,
                "message_id": response.message_id,
                "error": None,
            }

        await self._record_failure(
            communication_id=communication_id,
            channel_id=channel_id,
            provider_id=provider.get("id") if provider else None,
            error_message=response.error_message or "Provider failed",
            error_code=response.error_code,
        )
        return {
            "communication_id": communication_id,
            "channel": channel_name,
            "provider": provider_name or normalized_provider or "default",
            "status": "failed",
            "message_id": response.message_id,
            "error": response.error_message or response.error_code,
        }

    async def _record_failure(
        self,
        *,
        communication_id: int,
        channel_id: int,
        provider_id: Optional[int],
        error_message: str,
        error_code: Optional[str] = None,
    ) -> None:
        await supabase_client.update(
            "communications",
            {
                "status": "failed",
                "updated_at": datetime.utcnow().isoformat(),
                "retry_count": 1,
            },
            filters={"id": f"eq.{communication_id}"},
        )
        
        # Fetch the latest id for communication_attempts
        latest_attempts = await supabase_client.select(
            "communication_attempts",
            "id",
            limit=1,
            filters={"order": "id.desc"},
        )
        next_attempt_id = int(latest_attempts[0]["id"]) + 1 if latest_attempts else 1
        
        await supabase_client.insert(
            "communication_attempts",
            {
                "id": next_attempt_id,
                "communication_id": communication_id,
                "attempt_number": 1,
                "provider_id": provider_id,
                "status": "failed",
                "error_message": error_message,
                "error_code": error_code,
            },
        )
        await self._append_event(
            communication_id=communication_id,
            event_type="channel_failed",
            channel_id=channel_id,
            status="failed",
            metadata={"error": error_message, "error_code": error_code},
        )

    def _resolve_recipient(self, channel_name: str, candidate: dict[str, Any], payload: dict[str, Any]) -> str:
        if channel_name == "email":
            return payload.get("email") or candidate.get("email") or ""
        if channel_name == "sms":
            return payload.get("phone") or candidate.get("phone") or ""
        if channel_name == "voice":
            return payload.get("phone") or candidate.get("phone") or ""
        if channel_name == "whatsapp":
            return payload.get("whatsapp_number") or candidate.get("whatsapp_number") or candidate.get("phone") or ""
        if channel_name == "push":
            # Try payload first, then check if candidate has device_token in metadata
            device_token = payload.get("device_token") or (payload.get("data") or {}).get("device_token")
            if not device_token and candidate.get("metadata"):
                device_token = candidate.get("metadata", {}).get("device_token")
            return device_token or ""
        if channel_name == "slack":
            return payload.get("slack_channel") or payload.get("slack_user") or settings.slack_channel_id or ""
        if channel_name == "in_app":
            return str(candidate.get("id"))
        return payload.get("recipient") or ""

    async def _resolve_push_recipient(self, candidate: dict[str, Any], payload: dict[str, Any]) -> str:
        """Resolve push notification recipient by fetching device token from database."""
        payload_data = payload.get("data") or {}

        # Try explicit push token inputs first.
        direct_tokens = self._extract_push_tokens(
            payload.get("device_tokens"),
            payload_data.get("device_tokens"),
            payload.get("device_token"),
            payload_data.get("device_token"),
        )
        if direct_tokens:
            return direct_tokens[0]
        
        # Check candidate metadata
        if candidate.get("metadata"):
            metadata_tokens = self._extract_push_tokens(
                candidate.get("metadata", {}).get("device_tokens"),
                candidate.get("metadata", {}).get("device_token"),
            )
            if metadata_tokens:
                return metadata_tokens[0]
        
        # Fetch from device_tokens table
        try:
            tokens = await supabase_client.select(
                "device_tokens",
                "token,platform,last_active",
                filters={
                    "client_id": f"eq.{candidate['client_id']}",
                    "user_id": f"eq.{candidate['id']}",
                    "is_active": "eq.true",
                    "order": "last_active.desc"
                },
                limit=1
            )
            
            if tokens:
                return tokens[0]["token"]
        except Exception as e:
            print(f"Error fetching device token: {e}")
        
        return ""

    def _extract_push_tokens(self, *values: Any) -> list[str]:
        tokens: list[str] = []
        for value in values:
            if isinstance(value, str):
                cleaned = value.strip()
                if cleaned:
                    tokens.append(cleaned)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, str):
                        cleaned = item.strip()
                        if cleaned:
                            tokens.append(cleaned)

        # Preserve order while removing duplicates.
        return list(dict.fromkeys(tokens))

    def _missing_recipient_error(self, channel_name: str) -> str:
        if channel_name == "push":
            return "No active push device token found for this candidate"
        return f"No recipient available for channel '{channel_name}'"

    def _normalize_provider_name(self, provider_name: Optional[str]) -> Optional[str]:
        mapping = {
            "twilio_sms": "twilio",
            "twilio_whatsapp": "twilio",
            "twilio_voice": "twilio",
            "sendgrid": "mailgun",
        }
        if not provider_name:
            return None
        return mapping.get(provider_name, provider_name)

    def _stringify(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, (dict, list)):
            return json.dumps(value)
        return str(value)
