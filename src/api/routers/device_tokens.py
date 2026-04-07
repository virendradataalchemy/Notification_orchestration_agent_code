from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from src.api.dependencies import get_authenticated_client
from src.models import Client
from src.core.supabase import supabase_client
from datetime import datetime

router = APIRouter(prefix="/device-tokens", tags=["device-tokens"])


class RegisterDeviceTokenRequest(BaseModel):
    candidate_id: int
    device_token: str
    platform: str = "unknown"  # ios, android, web


@router.post("/register")
async def register_device_token(
    request: RegisterDeviceTokenRequest,
    client: Client = Depends(get_authenticated_client)
):
    """Register a device token for push notifications."""
    try:
        # Verify candidate belongs to client
        candidates = await supabase_client.select(
            "candidates",
            "id,client_id",
            filters={"id": f"eq.{request.candidate_id}", "client_id": f"eq.{client.id}"},
            limit=1
        )
        
        if not candidates:
            raise HTTPException(status_code=404, detail="Candidate not found or doesn't belong to this client")
        
        # Check if token already exists
        existing = await supabase_client.select(
            "device_tokens",
            "id,is_active",
            filters={
                "candidate_id": f"eq.{request.candidate_id}",
                "device_token": f"eq.{request.device_token}"
            },
            limit=1
        )
        
        if existing:
            # Update existing token
            await supabase_client.update(
                "device_tokens",
                {
                    "is_active": True,
                    "platform": request.platform,
                    "last_used_at": datetime.utcnow().isoformat(),
                    "updated_at": datetime.utcnow().isoformat()
                },
                filters={"id": f"eq.{existing[0]['id']}"}
            )
            
            return {
                "status": "updated",
                "message": "Device token updated successfully",
                "token_id": existing[0]["id"]
            }
        else:
            # Insert new token
            latest = await supabase_client.select(
                "device_tokens",
                "id",
                limit=1,
                filters={"order": "id.desc"}
            )
            next_id = int(latest[0]["id"]) + 1 if latest else 1
            
            result = await supabase_client.insert(
                "device_tokens",
                {
                    "id": next_id,
                    "candidate_id": request.candidate_id,
                    "device_token": request.device_token,
                    "platform": request.platform,
                    "is_active": True,
                    "last_used_at": datetime.utcnow().isoformat(),
                    "created_at": datetime.utcnow().isoformat(),
                    "updated_at": datetime.utcnow().isoformat()
                }
            )
            
            return {
                "status": "registered",
                "message": "Device token registered successfully",
                "token_id": result[0]["id"]
            }
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to register device token: {str(e)}")


@router.get("/candidate/{candidate_id}")
async def get_candidate_tokens(
    candidate_id: int,
    client: Client = Depends(get_authenticated_client)
):
    """Get all device tokens for a candidate."""
    try:
        # Verify candidate belongs to client
        candidates = await supabase_client.select(
            "candidates",
            "id,client_id",
            filters={"id": f"eq.{candidate_id}", "client_id": f"eq.{client.id}"},
            limit=1
        )
        
        if not candidates:
            raise HTTPException(status_code=404, detail="Candidate not found")
        
        tokens = await supabase_client.select(
            "device_tokens",
            "id,device_token,platform,is_active,last_used_at,created_at",
            filters={"candidate_id": f"eq.{candidate_id}"}
        )
        
        return {
            "candidate_id": candidate_id,
            "tokens": tokens,
            "active_count": sum(1 for t in tokens if t.get("is_active"))
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch device tokens: {str(e)}")


@router.delete("/{token_id}")
async def deactivate_device_token(
    token_id: int,
    client: Client = Depends(get_authenticated_client)
):
    """Deactivate a device token."""
    try:
        await supabase_client.update(
            "device_tokens",
            {
                "is_active": False,
                "updated_at": datetime.utcnow().isoformat()
            },
            filters={"id": f"eq.{token_id}"}
        )
        
        return {"status": "success", "message": "Device token deactivated"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to deactivate token: {str(e)}")
