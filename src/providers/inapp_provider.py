"""In-app notification provider - memory based with optional Supabase persistence."""

from src.providers.base import NotificationProvider, ProviderResponse, ProviderStatus, Message
from datetime import datetime
from typing import Dict, List

# In-memory storage
_inapp_storage: Dict[str, List[dict]] = {}


class InAppProvider(NotificationProvider):

    async def send(self, message: Message) -> ProviderResponse:
        notification_id = message.metadata.get("notification_id")
        if not notification_id:
            return ProviderResponse(status=ProviderStatus.FAILED, error_code="missing_id",
                                    error_message="notification_id is required")
        try:
            user_key = str(message.recipient)
            payload = {
                "id": notification_id,
                "subject": message.subject,
                "body": message.body,
                "data": message.data,
                "read": False,
                "created_at": datetime.utcnow().isoformat(),
                "recipient": message.recipient,
            }
            if user_key not in _inapp_storage:
                _inapp_storage[user_key] = []
            _inapp_storage[user_key].insert(0, payload)
            _inapp_storage[user_key] = _inapp_storage[user_key][:50]

            return ProviderResponse(status=ProviderStatus.SUCCESS, message_id=notification_id,
                                    metadata={"channel": "inapp", "storage": "memory"})
        except Exception as e:
            return ProviderResponse(status=ProviderStatus.FAILED, error_code="STORAGE_ERROR",
                                    error_message=str(e))

    async def get_status(self, message_id: str) -> ProviderResponse:
        for user_notifications in _inapp_storage.values():
            for n in user_notifications:
                if n.get("id") == message_id:
                    return ProviderResponse(status=ProviderStatus.SUCCESS, message_id=message_id,
                                            metadata={"read_status": "read" if n.get("read") else "unread"})
        return ProviderResponse(status=ProviderStatus.FAILED, message_id=message_id,
                                error_code="not_found", error_message="Notification not found")

    async def validate_recipient(self, recipient: str) -> bool:
        return bool(recipient and isinstance(recipient, str))

    def supports_channel(self) -> str:
        return "inapp"


async def get_user_notifications(user_id: str, limit: int = 20) -> List[dict]:
    return _inapp_storage.get(str(user_id), [])[:limit]


async def mark_as_read(user_id: str, notification_id: str) -> bool:
    user_key = str(user_id)
    if user_key in _inapp_storage:
        for n in _inapp_storage[user_key]:
            if n.get("id") == notification_id:
                n["read"] = True
                n["read_at"] = datetime.utcnow().isoformat()
                return True
    return False


async def get_unread_count(user_id: str) -> int:
    return sum(1 for n in _inapp_storage.get(str(user_id), []) if not n.get("read", False))
