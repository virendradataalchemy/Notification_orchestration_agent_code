from src.providers.base import NotificationProvider, ProviderResponse, ProviderStatus, Message
from src.core.redis import get_redis_client
import json


class InAppProvider(NotificationProvider):

    async def send(self, message: Message) -> ProviderResponse:
        redis = await get_redis_client()

        notification_id = message.metadata.get("notification_id")

        if not notification_id:
            return ProviderResponse(
                status=ProviderStatus.FAILED,
                error_code="missing_id",
                error_message="notification_id is required"
            )

        key = f"inapp:{message.recipient}:{notification_id}"

        payload = {
            "id": notification_id,
            "subject": message.subject,
            "body": message.body,
            "data": message.data,
            "read": False
        }

        await redis.set(key, json.dumps(payload))

        # Add to user list
        await redis.lpush(f"inapp:list:{message.recipient}", notification_id)

        # Increment unread count
        await redis.incr(f"inapp:unread:{message.recipient}")

        # Publish event (real-time)
        await redis.publish(
            f"notifications:{message.recipient}",
            json.dumps(payload)
        )

        return ProviderResponse(
            status=ProviderStatus.SUCCESS,
            message_id=notification_id,
            metadata={"channel": "inapp"}
        )

    async def get_status(self, message_id: str) -> ProviderResponse:
        redis = await get_redis_client()

        keys = await redis.keys(f"inapp:*:{message_id}")

        if not keys:
            return ProviderResponse(
                status=ProviderStatus.FAILED,
                message_id=message_id,
                error_code="not_found",
                error_message="Notification not found"
            )

        data = await redis.get(keys[0])
        notification = json.loads(data)

        status = "read" if notification.get("read") else "unread"

        return ProviderResponse(
            status=ProviderStatus.SUCCESS,
            message_id=message_id,
            metadata={"read_status": status}
        )

    async def validate_recipient(self, recipient: str) -> bool:
        # In-app = user_id → just check non-empty
        return bool(recipient and isinstance(recipient, str))

    def supports_channel(self) -> str:
        return "inapp"


# """In-app notification provider for real-time user notifications."""

# import asyncio
# from typing import Dict, List, Optional
# from datetime import datetime
# import json

# from .base import NotificationProvider, Message, ProviderResponse, ProviderStatus
# from src.core.redis import get_redis_client


# class InAppProvider(NotificationProvider):
#     """
#     In-app notification provider.

#     Stores notifications in Redis for real-time delivery to connected clients.
#     Can be consumed via WebSocket connections or REST API polling.
#     """

#     def __init__(self, config: dict = None):
#         super().__init__(config)
#         self.ttl_seconds = 86400 * 30  # 30 days retention

#     async def send(self, message: Message) -> ProviderResponse:
#         """
#         Send in-app notification.

#         Stores notification in Redis for the user to retrieve.

#         Args:
#             message: In-app message to send
#                      recipient should be user_id

#         Returns:
#             ProviderResponse with notification ID
#         """
#         try:
#             redis_client = await get_redis_client()

#             # Create notification payload
#             notification = {
#                 'id': message.metadata.get('notification_id', 'unknown'),
#                 'user_id': message.recipient,
#                 'title': message.subject or 'Notification',
#                 'body': message.body,
#                 'type': message.metadata.get('type', 'info'),
#                 'priority': message.metadata.get('priority', 'medium'),
#                 'data': message.data or {},
#                 'timestamp': datetime.utcnow().isoformat(),
#                 'read': False,
#                 'clicked': False,
#             }

#             # Store in Redis
#             # Key format: inapp:{user_id}:{notification_id}
#             key = f"inapp:{message.recipient}:{notification['id']}"
#             await redis_client.setex(
#                 key,
#                 self.ttl_seconds,
#                 json.dumps(notification)
#             )

#             # Add to user's notification list (sorted set by timestamp)
#             list_key = f"inapp:list:{message.recipient}"
#             score = datetime.utcnow().timestamp()
#             await redis_client.zadd(
#                 list_key,
#                 {notification['id']: score}
#             )

#             # Set expiry on list
#             await redis_client.expire(list_key, self.ttl_seconds)

#             # Increment unread counter
#             counter_key = f"inapp:unread:{message.recipient}"
#             await redis_client.incr(counter_key)
#             await redis_client.expire(counter_key, self.ttl_seconds)

#             # Publish to Redis pub/sub for real-time delivery
#             channel = f"notifications:{message.recipient}"
#             await redis_client.publish(
#                 channel,
#                 json.dumps(notification)
#             )

#             return ProviderResponse(
#                 status=ProviderStatus.SUCCESS,
#                 message_id=notification['id'],
#                 metadata={
#                     'provider': 'inapp',
#                     'stored_in': 'redis',
#                     'pubsub_channel': channel
#                 }
#             )

#         except Exception as e:
#             return ProviderResponse(
#                 status=ProviderStatus.FAILED,
#                 error_code="REDIS_ERROR",
#                 error_message=f"Failed to store in-app notification: {str(e)}"
#             )

#     async def get_user_notifications(
#         self,
#         user_id: str,
#         limit: int = 20,
#         offset: int = 0
#     ) -> List[Dict]:
#         """
#         Get user's in-app notifications.

#         Args:
#             user_id: User ID
#             limit: Max notifications to return
#             offset: Offset for pagination

#         Returns:
#             List of notification dictionaries
#         """
#         try:
#             redis_client = await get_redis_client()

#             # Get notification IDs from sorted set
#             list_key = f"inapp:list:{user_id}"
#             notification_ids = await redis_client.zrevrange(
#                 list_key,
#                 offset,
#                 offset + limit - 1
#             )

#             # Retrieve each notification
#             notifications = []
#             for notif_id in notification_ids:
#                 key = f"inapp:{user_id}:{notif_id}"
#                 data = await redis_client.get(key)
#                 if data:
#                     notifications.append(json.loads(data))

#             return notifications

#         except Exception as e:
#             print(f"Error retrieving notifications: {e}")
#             return []

#     async def mark_as_read(self, user_id: str, notification_id: str) -> bool:
#         """
#         Mark notification as read.

#         Args:
#             user_id: User ID
#             notification_id: Notification ID

#         Returns:
#             True if successful
#         """
#         try:
#             redis_client = await get_redis_client()

#             key = f"inapp:{user_id}:{notification_id}"
#             data = await redis_client.get(key)

#             if data:
#                 notification = json.loads(data)
#                 if not notification['read']:
#                     notification['read'] = True
#                     notification['read_at'] = datetime.utcnow().isoformat()

#                     # Update notification
#                     await redis_client.setex(
#                         key,
#                         self.ttl_seconds,
#                         json.dumps(notification)
#                     )

#                     # Decrement unread counter
#                     counter_key = f"inapp:unread:{user_id}"
#                     await redis_client.decr(counter_key)

#                 return True

#             return False

#         except Exception as e:
#             print(f"Error marking as read: {e}")
#             return False

#     async def get_unread_count(self, user_id: str) -> int:
#         """
#         Get count of unread notifications.

#         Args:
#             user_id: User ID

#         Returns:
#             Number of unread notifications
#         """
#         try:
#             redis_client = await get_redis_client()
#             counter_key = f"inapp:unread:{user_id}"
#             count = await redis_client.get(counter_key)
#             return int(count) if count else 0

#         except Exception:
#             return 0

#     async def delete_notification(self, user_id: str, notification_id: str) -> bool:
#         """
#         Delete a notification.

#         Args:
#             user_id: User ID
#             notification_id: Notification ID

#         Returns:
#             True if successful
#         """
#         try:
#             redis_client = await get_redis_client()

#             # Remove from storage
#             key = f"inapp:{user_id}:{notification_id}"
#             await redis_client.delete(key)

#             # Remove from list
#             list_key = f"inapp:list:{user_id}"
#             await redis_client.zrem(list_key, notification_id)

#             return True

#         except Exception:
#             return False

#     async def validate_recipient(self, recipient: str) -> bool:
#         """
#         Validate user ID format.

#         Args:
#             recipient: User ID

#         Returns:
#             True if valid
#         """
#         return bool(recipient and isinstance(recipient, str) and len(recipient) > 0)

#     def supports_channel(self) -> str:
#         """Returns 'inapp'."""
#         return "inapp"
