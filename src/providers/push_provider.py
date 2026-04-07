import firebase_admin
from firebase_admin import credentials, messaging
from typing import List
import os

from .base import NotificationProvider, Message, ProviderResponse, ProviderStatus
from src.config import settings
from src.core.supabase import supabase_client
from datetime import datetime


class PushProvider(NotificationProvider):
    """Push notification provider using Firebase Cloud Messaging."""

    def __init__(self, config: dict = None):
        super().__init__(config)
        self._initialized = False

        # Initialize Firebase Admin SDK
        if settings.firebase_credentials_path:
            try:
                # Check if file exists
                if not os.path.exists(settings.firebase_credentials_path):
                    print(f"Warning: Firebase credentials file not found: {settings.firebase_credentials_path}")
                    return

                # Check if already initialized
                try:
                    firebase_admin.get_app()
                    self._initialized = True
                except ValueError:
                    # Not initialized, initialize now
                    cred = credentials.Certificate(settings.firebase_credentials_path)
                    firebase_admin.initialize_app(cred)
                    self._initialized = True
                    print(f"Firebase initialized with credentials from: {settings.firebase_credentials_path}")
            except Exception as e:
                print(f"Error initializing Firebase: {e}")
                pass

    async def send(self, message: Message) -> ProviderResponse:
        """
        Send push notification via FCM or Web Notifications API.

        Args:
            message: Push notification to send
                     recipient should be device token
                     data should contain notification payload

        Returns:
            ProviderResponse with FCM message ID
        """
        # Check if this is a web browser token (starts with 'web_')
        if message.recipient and message.recipient.startswith('web_'):
            # For web tokens, we can't send from backend - it's handled by browser
            # Just store the token and return success
            try:
                candidate_id = message.metadata.get('candidate_id')
                if candidate_id and message.recipient:
                    await self._store_device_token(candidate_id, message.recipient, platform='web')
                
                return ProviderResponse(
                    status=ProviderStatus.SUCCESS,
                    message_id=f"web_push_{message.recipient[-12:]}",
                    metadata={
                        'provider': 'web_push',
                        'note': 'Web push handled by browser',
                        'stored_token': True
                    }
                )
            except Exception as e:
                return ProviderResponse(
                    status=ProviderStatus.FAILED,
                    error_code="WEB_PUSH_ERROR",
                    error_message=str(e)
                )
        
        # For mobile tokens, use Firebase
        if not self._initialized:
            return ProviderResponse(
                status=ProviderStatus.FAILED,
                error_code="NOT_CONFIGURED",
                error_message="Firebase credentials not configured"
            )

        try:
            # Build notification
            notification_data = message.data or {}

            # Ensure body is not empty
            body_text = message.body or notification_data.get('body', '')
            if not body_text:
                body_text = notification_data.get('message', '') or f"Push: {message.subject or 'Notification'}"

            fcm_message = messaging.Message(
                notification=messaging.Notification(
                    title=message.subject or notification_data.get('title', 'Notification'),
                    body=body_text,
                    image=notification_data.get('image')
                ),
                data=notification_data.get('data', {}),
                token=message.recipient,
                android=messaging.AndroidConfig(
                    priority='high',
                    notification=messaging.AndroidNotification(
                        sound='default',
                        color=notification_data.get('color', '#FF0000')
                    )
                ),
                apns=messaging.APNSConfig(
                    payload=messaging.APNSPayload(
                        aps=messaging.Aps(
                            sound='default',
                            badge=notification_data.get('badge', 1)
                        )
                    )
                ),
            )

            # Send message
            response = messaging.send(fcm_message)

            # Store device token in database if we have candidate info
            try:
                candidate_id = message.metadata.get('candidate_id')
                if candidate_id and message.recipient:
                    await self._store_device_token(candidate_id, message.recipient)
                    await self._store_device_token(candidate_id, message.recipient)
            except Exception as db_error:
                print(f"Warning: Failed to store device token: {db_error}")

            return ProviderResponse(
                status=ProviderStatus.SUCCESS,
                message_id=response,
                metadata={'provider': 'fcm', 'stored_token': True}
            )

        except firebase_admin.exceptions.FirebaseError as e:
            # Handle all Firebase-specific errors
            error_code = "FIREBASE_ERROR"
            if "unregistered" in str(e).lower():
                error_code = "UNREGISTERED_DEVICE"
            elif "invalid" in str(e).lower():
                error_code = "INVALID_ARGUMENT"

            return ProviderResponse(
                status=ProviderStatus.FAILED,
                error_code=error_code,
                error_message=str(e)
            )

        except Exception as e:
            return ProviderResponse(
                status=ProviderStatus.FAILED,
                error_code="UNKNOWN_ERROR",
                error_message=str(e)
            )

    async def _store_device_token(self, candidate_id: int, device_token: str, platform: str = "unknown"):
        """Store device token in database."""
        try:
            # Check if token already exists
            existing = await supabase_client.select(
                "device_tokens",
                "id,is_active",
                filters={"candidate_id": f"eq.{candidate_id}", "device_token": f"eq.{device_token}"},
                limit=1
            )
            
            if existing:
                # Update last_used_at
                await supabase_client.update(
                    "device_tokens",
                    {
                        "last_used_at": datetime.utcnow().isoformat(),
                        "is_active": True,
                        "platform": platform,
                        "updated_at": datetime.utcnow().isoformat()
                    },
                    filters={"id": f"eq.{existing[0]['id']}"}
                )
            else:
                # Insert new token
                latest = await supabase_client.select(
                    "device_tokens",
                    "id",
                    limit=1,
                    filters={"order": "id.desc"}
                )
                next_id = int(latest[0]["id"]) + 1 if latest else 1
                
                await supabase_client.insert(
                    "device_tokens",
                    {
                        "id": next_id,
                        "candidate_id": candidate_id,
                        "device_token": device_token,
                        "platform": platform,
                        "is_active": True,
                        "last_used_at": datetime.utcnow().isoformat(),
                        "created_at": datetime.utcnow().isoformat(),
                        "updated_at": datetime.utcnow().isoformat()
                    }
                )
        except Exception as e:
            print(f"Error storing device token: {e}")
            # Don't fail the notification if token storage fails

    async def send_multicast(self, message: Message, tokens: List[str]) -> ProviderResponse:
        """
        Send push notification to multiple devices.

        Args:
            message: Push notification
            tokens: List of device tokens

        Returns:
            ProviderResponse with batch result
        """
        if not self._initialized:
            return ProviderResponse(
                status=ProviderStatus.FAILED,
                error_code="NOT_CONFIGURED"
            )

        try:
            notification_data = message.data or {}

            multicast_message = messaging.MulticastMessage(
                notification=messaging.Notification(
                    title=message.subject or 'Notification',
                    body=message.body
                ),
                data=notification_data.get('data', {}),
                tokens=tokens,
            )

            response = messaging.send_multicast(multicast_message)

            return ProviderResponse(
                status=ProviderStatus.SUCCESS,
                metadata={
                    'provider': 'fcm',
                    'success_count': response.success_count,
                    'failure_count': response.failure_count
                }
            )

        except Exception as e:
            return ProviderResponse(
                status=ProviderStatus.FAILED,
                error_code="UNKNOWN_ERROR",
                error_message=str(e)
            )

    async def get_status(self, message_id: str) -> ProviderResponse:
        """
        Get push notification status.

        Note: FCM doesn't provide status check after sending.
        Status is returned immediately upon send.
        """
        return ProviderResponse(
            status=ProviderStatus.SUCCESS,
            message_id=message_id,
            metadata={'note': 'FCM status known at send time'}
        )

    async def validate_recipient(self, recipient: str) -> bool:
        """
        Validate FCM device token format.

        Args:
            recipient: FCM device token

        Returns:
            True if non-empty string
        """
        return bool(recipient and isinstance(recipient, str) and len(recipient) > 10)

    def supports_channel(self) -> str:
        """Returns 'push'."""
        return "push"
