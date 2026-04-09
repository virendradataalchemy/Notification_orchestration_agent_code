"""API router for intelligent orchestration agent."""

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
import logging

from src.api.dependencies import get_authenticated_client
from src.models import Client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/orchestrate", tags=["orchestration"])
templates = Jinja2Templates(directory="src/templates")


class OrchestrationRequest(BaseModel):
    """Request schema for orchestration."""
    message_content: str = Field(..., max_length=10000, description="Message content to send")
    user_id: Optional[str] = Field(None, description="Optional user ID to send notification to")
    email: Optional[str] = Field(None, description="Direct email recipient when user_id is not provided")
    phone: Optional[str] = Field(None, description="Direct mobile recipient when user_id is not provided")
    whatsapp_number: Optional[str] = Field(None, description="Direct WhatsApp recipient when user_id is not provided")
    slack_channel: Optional[str] = Field(None, description="Direct Slack channel or user recipient when user_id is not provided")
    idempotency_key: Optional[str] = Field(None, description="Optional key for deduplication")
    custom_variables: Optional[Dict[str, Any]] = Field(None, description="Optional custom variables for template")


class OrchestrationResponse(BaseModel):
    """Response schema for orchestration."""
    status: str
    selected_template: Optional[Dict[str, Any]] = None
    urgency: Optional[str] = None
    priority_order: Optional[list[str]] = None
    delivery_status: Optional[str] = None
    channel_used: Optional[str] = None
    reasoning: Optional[Dict[str, Any]] = None
    processing_time_ms: int
    error: Optional[str] = None


@router.post("/send", response_model=OrchestrationResponse)
async def orchestrate_send(
    request: OrchestrationRequest,
    client: Client = Depends(get_authenticated_client)
):
    """
    Orchestrate intelligent notification sending using IntelligentOrchestrationAgent.
    
    Pipeline:
    1. Fetches user/candidate details
    2. LLM selects best template
    3. LLM determines channel priority
    4. Executes real delivery via SupabaseNotificationService
    5. Returns results with reasoning
    """
    try:
        from src.services.intelligent_orchestration_agent import IntelligentOrchestrationAgent

        agent = IntelligentOrchestrationAgent(client_id=client.id)

        result = await agent.orchestrate_send(
            message_content=request.message_content,
            user_id=request.user_id.strip() if request.user_id else None,
            idempotency_key=request.idempotency_key,
            custom_variables=request.custom_variables,
            recipient_overrides={
                "email": request.email,
                "phone": request.phone,
                "whatsapp_number": request.whatsapp_number,
                "slack_channel": request.slack_channel,
            },
        )

        if result.get('status') == 'error':
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.get('error', 'Orchestration failed')
            )

        return OrchestrationResponse(
            status=result['status'],
            selected_template=result.get('selected_template'),
            urgency=result.get('urgency'),
            priority_order=result.get('priority_order'),
            delivery_status=result.get('delivery_status'),
            channel_used=result.get('channel_used'),
            reasoning=result.get('reasoning'),
            processing_time_ms=result.get('processing_time_ms', 0),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Orchestration endpoint error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )


# Dedicated orchestration page route
@router.get("/page/{client_id}", response_class=HTMLResponse, include_in_schema=False)
async def orchestration_page(request: Request, client_id: str):
    """Render dedicated orchestration page."""
    return templates.TemplateResponse(
        request, "orchestration_page.html",
        {"client_id": client_id}
    )
