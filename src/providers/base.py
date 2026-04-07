from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum


class ProviderStatus(str, Enum):
    """Provider response status."""
    SUCCESS = "success"
    FAILED = "failed"
    PENDING = "pending"


@dataclass
class ProviderResponse:
    """Standard response from a notification provider."""
    status: ProviderStatus
    message_id: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class Message:
    """Standard message format for all providers."""
    recipient: str  # Email, phone, user_id, etc.
    subject: Optional[str] = None
    body: str = ""
    data: Dict[str, Any] = None
    attachments: list = None
    metadata: Dict[str, Any] = None   # ✅ ADD THIS

    def __post_init__(self):
        if self.data is None:
            self.data = {}
        if self.attachments is None:
            self.attachments = []
        if self.metadata is None:     # ✅ ADD THIS
            self.metadata = {}


class NotificationProvider(ABC):
    """Abstract base class for notification providers."""

    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize provider with configuration.

        Args:
            config: Provider-specific configuration
        """
        self.config = config or {}

    @abstractmethod
    async def send(self, message: Message) -> ProviderResponse:
        """
        Send a notification message.

        Args:
            message: Message to send

        Returns:
            ProviderResponse with delivery status
        """
        pass

    @abstractmethod
    async def get_status(self, message_id: str) -> ProviderResponse:
        """
        Get delivery status for a message.

        Args:
            message_id: Provider's message identifier

        Returns:
            ProviderResponse with current status
        """
        pass

    @abstractmethod
    async def validate_recipient(self, recipient: str) -> bool:
        """
        Validate recipient format/availability.

        Args:
            recipient: Recipient identifier

        Returns:
            True if valid, False otherwise
        """
        pass

    @abstractmethod
    def supports_channel(self) -> str:
        """
        Get the channel this provider supports.

        Returns:
            Channel name (email, sms, etc.)
        """
        pass
