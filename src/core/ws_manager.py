import asyncio
import json
import logging
from contextlib import suppress
from typing import Dict, Set
from fastapi import WebSocket

from src.core.redis import get_redis_client

logger = logging.getLogger(__name__)
TENANT_EVENT_CHANNEL = "tenant:ws:events"

class ConnectionManager:
    def __init__(self):
        # Maps tenant_id to a set of active WebSockets
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        self._pubsub_task: asyncio.Task | None = None
        self._pubsub = None

    async def connect(self, websocket: WebSocket, tenant_id: str):
        await websocket.accept()
        if tenant_id not in self.active_connections:
            self.active_connections[tenant_id] = set()
        self.active_connections[tenant_id].add(websocket)
        logger.info(f"New WebSocket connection for tenant {tenant_id}. Total: {len(self.active_connections[tenant_id])}")

    def disconnect(self, websocket: WebSocket, tenant_id: str):
        if tenant_id in self.active_connections:
            self.active_connections[tenant_id].discard(websocket)
            if not self.active_connections[tenant_id]:
                del self.active_connections[tenant_id]
        logger.info(f"WebSocket disconnected for tenant {tenant_id}")

    async def broadcast_to_tenant(self, tenant_id: str, message: dict):
        if tenant_id in self.active_connections:
            disconnected = set()
            for connection in self.active_connections[tenant_id]:
                try:
                    await connection.send_json(message)
                except Exception as e:
                    logger.error(f"Error sending message to WebSocket: {e}")
                    disconnected.add(connection)
            
            for conn in disconnected:
                self.disconnect(conn, tenant_id)

    async def publish_to_tenant(self, tenant_id: str, message: dict):
        """
        Publish an event through Redis so API websocket processes and Celery
        workers can communicate through a shared channel.
        """
        payload = {"tenant_id": tenant_id, "message": message}
        try:
            redis = await get_redis_client()
            await redis.publish(TENANT_EVENT_CHANNEL, json.dumps(payload))
        except Exception as exc:
            logger.warning("Redis pubsub unavailable, falling back to local websocket broadcast: %s", exc)
            await self.broadcast_to_tenant(tenant_id, message)

    async def start_pubsub_listener(self):
        if self._pubsub_task and not self._pubsub_task.done():
            return
        self._pubsub_task = asyncio.create_task(self._run_pubsub_listener())

    async def stop_pubsub_listener(self):
        if self._pubsub_task:
            self._pubsub_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._pubsub_task
            self._pubsub_task = None

        if self._pubsub is not None:
            with suppress(Exception):
                await self._pubsub.close()
            self._pubsub = None

    async def _run_pubsub_listener(self):
        try:
            redis = await get_redis_client()
            self._pubsub = redis.pubsub()
            await self._pubsub.subscribe(TENANT_EVENT_CHANNEL)
            logger.info("WebSocket pubsub listener subscribed to Redis channel")

            while True:
                message = await self._pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if not message:
                    await asyncio.sleep(0.1)
                    continue

                data = message.get("data")
                if not data:
                    continue

                try:
                    payload = json.loads(data)
                    tenant_id = payload.get("tenant_id")
                    tenant_message = payload.get("message") or {}
                    if tenant_id:
                        await self.broadcast_to_tenant(tenant_id, tenant_message)
                except Exception as exc:
                    logger.error("Failed to process websocket pubsub message: %s", exc, exc_info=True)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("WebSocket pubsub listener stopped unexpectedly: %s", exc, exc_info=True)
        finally:
            if self._pubsub is not None:
                with suppress(Exception):
                    await self._pubsub.close()
                self._pubsub = None

manager = ConnectionManager()
