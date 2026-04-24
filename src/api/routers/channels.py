"""Channel capability discovery endpoints."""

from fastapi import APIRouter

from src.api.schemas import ChannelCapabilitiesResponse
from src.services.channel_policy import get_channel_capabilities

router = APIRouter(prefix="/channels", tags=["channels"])


@router.get(
    "/capabilities",
    response_model=ChannelCapabilitiesResponse,
    summary="Get channel capabilities",
    description=(
        "Returns per-channel policy/capability metadata for API clients, "
        "including template requirements and recipient field requirements."
    ),
)
async def get_capabilities():
    return ChannelCapabilitiesResponse(channels=get_channel_capabilities())
