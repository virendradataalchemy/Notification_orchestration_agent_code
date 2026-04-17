"""
Public API for external applications to trigger intelligent notifications.

Authentication: Bearer <sk_live_...> via Authorization header
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any, Dict, Optional

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from src.core import supabase_client
from src.core.supabase import CLIENTS_TABLE
from src.models import Client
from src.services.intelligent_orchestration_agent import IntelligentOrchestrationAgent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integration", tags=["external-api"])


# ── API Key Auth ──────────────────────────────────────────────────────────────

def _hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


async def _client_from_supabase(filters: dict) -> Client | None:
    rows = await supabase_client.select(
        CLIENTS_TABLE,
        "id,name,default_language,logo_url,brand_color,is_active,client_slug,created_at,updated_at",
        limit=1,
        filters=filters,
    )
    if not rows:
        return None
    r = rows[0]
    c = Client(
        id=r["id"], name=r["name"],
        default_language=r.get("default_language"),
        logo_url=r.get("logo_url"),
        brand_color=r.get("brand_color"),
        is_active=r.get("is_active", True),
        client_slug=r.get("client_slug"),
    )
    return c


async def get_client_from_api_key(
    authorization: Optional[str] = Header(None),
    x_client_id: Optional[str] = Header(None),
) -> Client:
    """
    Validate Bearer API key and return the associated client.
    - Production: Authorization: Bearer sk_live_1_xxxx...
    - Dev/Test:   X-Client-Id: 1  (only when DEBUG=true)
    """
    from src.config import settings

    # Dev mode shortcut — X-Client-Id header
    if x_client_id and settings.debug:
        client = await _client_from_supabase({"id": f"eq.{x_client_id}", "is_active": "eq.true"})
        if not client:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Client {x_client_id} not found")
        logger.info("🔧  Dev auth  client=%s (%s)", client.id, client.name)
        return client

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key. Use: Authorization: Bearer <your_api_key>",
            headers={"WWW-Authenticate": "Bearer"},
        )

    api_key = authorization.removeprefix("Bearer ").strip()
    if not api_key.startswith("sk_"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key format. Keys start with sk_live_ or sk_test_",
        )

    key_hash = _hash(api_key)
    try:
        client = await _client_from_supabase({"api_key_hash": f"eq.{key_hash}", "is_active": "eq.true"})
    except httpx.HTTPStatusError as exc:
        if exc.response is not None and exc.response.status_code == 400:
            logger.error("API key auth lookup failed because the clients table is missing API key columns")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="API key authentication is not available because the clients table is missing api_key columns",
            ) from exc
        raise

    if not client:
        logger.warning("Invalid API key attempt: prefix=%s", api_key[:20])
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or revoked API key",
        )

    logger.info("🔑  API key auth  client=%s (%s)", client.id, client.name)
    return client


# ── Request / Response schemas ────────────────────────────────────────────────

class TriggerRequest(BaseModel):
    message: str = Field(..., description="Notification content / message body")
    candidate_id: Optional[int] = Field(None, description="Candidate primary key in the clients.candidates table")
    user_id: Optional[str] = Field(None, description="Legacy alias for candidate id as a string")
    to: Optional[Dict[str, str]] = Field(None, description="Direct recipient contacts. Keys: email, phone, whatsapp_number, slack_channel")
    overrides: Optional[Dict[str, str]] = Field(None, description="Alias for 'to' — same format")
    variables: Optional[Dict[str, Any]] = Field(None, description="Template variables for rendering")
    idempotency_key: Optional[str] = Field(None, description="Unique key to prevent duplicate sends")


class TriggerResponse(BaseModel):
    success: bool
    message: str
    delivery_status: Optional[str] = None
    channel_used: Optional[str] = None
    template_used: Optional[str] = None
    urgency_level: Optional[str] = None
    priority_order: Optional[list] = None
    processing_time_ms: Optional[int] = None


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.post("/trigger", response_model=TriggerResponse, summary="Trigger a notification")
async def trigger_notification(
    request: TriggerRequest,
    client: Client = Depends(get_client_from_api_key),
):
    """
    Trigger an intelligent notification from any external application.

    ```
    curl -X POST https://your-domain/api/v1/integration/trigger \\
      -H "Authorization: Bearer sk_live_1_xxxx" \\
      -H "Content-Type: application/json" \\
      -d '{"message": "Your OTP is 1234", "to": {"email": "user@example.com"}}'
    ```
    """
    try:
        agent = IntelligentOrchestrationAgent(client_id=client.id)

        overrides = request.to or request.overrides or {}
        resolved_user_id = str(request.candidate_id) if request.candidate_id is not None else request.user_id
        result = await agent.orchestrate_send(
            message_content=request.message,
            user_id=resolved_user_id,
            idempotency_key=request.idempotency_key,
            custom_variables=request.variables,
            recipient_overrides={
                "email": overrides.get("email"),
                "phone": overrides.get("phone"),
                "whatsapp_number": overrides.get("whatsapp_number"),
                "slack_channel": overrides.get("slack_channel") or overrides.get("slack_id"),
            },
        )

        if result.get("status") == "error":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.get("error", "Orchestration failed"),
            )

        template_name = (result.get("selected_template") or {}).get("template_name")
        delivery_status = str(result.get("delivery_status") or "").lower()
        success = delivery_status in {"sent", "delivered", "success"}
        response_message = {
            "sent": "Notification accepted by provider; final delivery may still be pending",
            "delivered": "Notification delivered successfully",
            "success": "Notification delivered successfully",
        }.get(delivery_status, "Notification orchestration completed but delivery failed")
        logger.info(
            "✅  Integration trigger  client=%s  channel=%s  template=%r  status=%s  %sms",
            client.id, result.get("channel_used"), template_name,
            result.get("delivery_status"), result.get("processing_time_ms"),
        )

        return TriggerResponse(
            success=success,
            message=response_message,
            delivery_status=result.get("delivery_status"),
            channel_used=result.get("channel_used"),
            template_used=template_name,
            urgency_level=result.get("urgency"),
            priority_order=result.get("priority_order"),
            processing_time_ms=result.get("processing_time_ms"),
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Integration API error: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while processing the request.",
        )
