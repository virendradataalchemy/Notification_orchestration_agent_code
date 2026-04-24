import firebase_admin
from firebase_admin import credentials, messaging
from typing import List
import os

from .base import NotificationProvider, Message, ProviderResponse, ProviderStatus
from src.config import settings


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
        Send push notification via FCM.

        Args:
            message: Push notification to send
                     recipient should be device token
                     data should contain notification payload

        Returns:
            ProviderResponse with FCM message ID
        """
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

            return ProviderResponse(
                status=ProviderStatus.SUCCESS,
                message_id=response,
                metadata={'provider': 'fcm'}
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
