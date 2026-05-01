from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
import logging
from src.core.ws_manager import manager

router = APIRouter(tags=["websocket"])
logger = logging.getLogger(__name__)

@router.websocket("/ws/{tenant_id}")
async def websocket_endpoint(websocket: WebSocket, tenant_id: str):
    await manager.connect(websocket, tenant_id)
    try:
        while True:
            # Keep the connection open and wait for messages from the client if needed
            # For now, we just wait for disconnection
            data = await websocket.receive_text()
            # We can handle client messages here if needed
    except WebSocketDisconnect:
        manager.disconnect(websocket, tenant_id)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket, tenant_id)
