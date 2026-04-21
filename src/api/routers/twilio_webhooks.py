"""Twilio webhook endpoints for call status and recording callbacks."""

from fastapi import APIRouter, Request, Form
from typing import Optional
import logging

from src.core import supabase_client

router = APIRouter(prefix="/api/webhooks/twilio", tags=["webhooks"])
logger = logging.getLogger(__name__)


@router.post("/voice-status")
async def voice_status_callback(
    CallSid: str = Form(...),
    CallStatus: str = Form(...),
    CallDuration: Optional[str] = Form(None),
    From: Optional[str] = Form(None),
    To: Optional[str] = Form(None),
):
    """
    Receive voice call status updates from Twilio.
    
    Twilio sends this webhook when call status changes:
    - initiated, ringing, answered, completed
    """
    try:
        logger.info(f"Voice status callback: CallSid={CallSid}, Status={CallStatus}, Duration={CallDuration}")
        
        # Find the communication by idempotency_key (which contains the CallSid)
        communications = await supabase_client.select(
            "communications",
            "id,status",
            filters={"idempotency_key": f"eq.{CallSid}"}
        )
        
        if not communications:
            logger.warning(f"Communication not found for CallSid: {CallSid}")
            return {"status": "ok", "message": "Communication not found"}
        
        communication_id = communications[0]["id"]
        
        # Map Twilio status to our status
        status_map = {
            "initiated": "initiated",
            "ringing": "ringing",
            "in-progress": "ringing",
            "answered": "ringing",
            "completed": "sent",
            "busy": "failed",
            "no-answer": "failed",
            "failed": "failed",
            "canceled": "failed"
        }
        
        new_status = status_map.get(CallStatus, "queued")
        
        # Update communication status
        await supabase_client.update(
            "communications",
            {"status": new_status},
            filters={"id": f"eq.{communication_id}"}
        )
        
        # Log event
        latest_events = await supabase_client.select(
            "notification_events",
            "id",
            limit=1,
            filters={"order": "id.desc"}
        )
        next_event_id = int(latest_events[0]["id"]) + 1 if latest_events else 1
        
        await supabase_client.insert(
            "notification_events",
            {
                "id": next_event_id,
                "communication_id": communication_id,
                "event_type": f"call_{CallStatus}",
                "channel_id": 2,  # voice channel
                "status": new_status,
                "metadata": {
                    "call_sid": CallSid,
                    "call_status": CallStatus,
                    "call_duration": CallDuration,
                    "from": From,
                    "to": To
                }
            }
        )
        
        return {"status": "ok", "message": "Status updated"}
        
    except Exception as e:
        logger.error(f"Error processing voice status callback: {str(e)}")
        return {"status": "error", "message": str(e)}


@router.post("/recording-status")
async def recording_status_callback(
    CallSid: str = Form(...),
    RecordingSid: str = Form(...),
    RecordingUrl: str = Form(...),
    RecordingStatus: str = Form(...),
    RecordingDuration: Optional[str] = Form(None),
    RecordingChannels: Optional[str] = Form(None),
):
    """
    Receive recording status updates from Twilio.
    
    Twilio sends this webhook when a recording is completed.
    """
    try:
        logger.info(f"Recording callback: CallSid={CallSid}, RecordingSid={RecordingSid}, Status={RecordingStatus}")
        
        # Find the communication by idempotency_key (which contains the CallSid)
        communications = await supabase_client.select(
            "communications",
            "id",
            filters={"idempotency_key": f"eq.{CallSid}"}
        )
        
        if not communications:
            logger.warning(f"Communication not found for CallSid: {CallSid}")
            return {"status": "ok", "message": "Communication not found"}
        
        communication_id = communications[0]["id"]
        
        # Update communication with recording info
        await supabase_client.update(
            "communications",
            {
                "recording_url": RecordingUrl,
                "recording_sid": RecordingSid,
                "recording_duration": int(RecordingDuration) if RecordingDuration else None
            },
            filters={"id": f"eq.{communication_id}"}
        )
        
        # Log recording event
        latest_events = await supabase_client.select(
            "notification_events",
            "id",
            limit=1,
            filters={"order": "id.desc"}
        )
        next_event_id = int(latest_events[0]["id"]) + 1 if latest_events else 1
        
        await supabase_client.insert(
            "notification_events",
            {
                "id": next_event_id,
                "communication_id": communication_id,
                "event_type": "recording_completed",
                "channel_id": 2,  # voice channel
                "status": "completed",
                "metadata": {
                    "recording_sid": RecordingSid,
                    "recording_url": RecordingUrl,
                    "recording_duration": RecordingDuration,
                    "recording_channels": RecordingChannels,
                    "recording_status": RecordingStatus
                }
            }
        )
        
        logger.info(f"Recording saved for communication {communication_id}: {RecordingUrl}")
        
        return {"status": "ok", "message": "Recording saved"}
        
    except Exception as e:
        logger.error(f"Error processing recording callback: {str(e)}")
        return {"status": "error", "message": str(e)}


@router.get("/recording/{recording_sid}")
async def get_recording_url(recording_sid: str):
    """Get the recording URL for a given recording SID."""
    try:
        communications = await supabase_client.select(
            "communications",
            "id,recording_url,recording_duration,recording_sid",
            filters={"recording_sid": f"eq.{recording_sid}"}
        )
        
        if not communications:
            return {"error": "Recording not found"}
        
        return {
            "recording_sid": recording_sid,
            "recording_url": communications[0]["recording_url"],
            "recording_duration": communications[0]["recording_duration"]
        }
        
    except Exception as e:
        logger.error(f"Error fetching recording: {str(e)}")
        return {"error": str(e)}
