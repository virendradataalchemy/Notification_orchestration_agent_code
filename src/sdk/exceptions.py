from __future__ import annotations

from fastapi import HTTPException


class NotificationPipelineError(Exception):
    """Base exception for direct-import notification pipeline usage."""

    def __init__(self, message: str, *, status_code: int = 500):
        super().__init__(message)
        self.message = message
        self.status_code = status_code

    def to_http_exception(self) -> HTTPException:
        """Convert library exception into an HTTP exception for API adapters."""
        return HTTPException(status_code=self.status_code, detail=self.message)


class ValidationError(NotificationPipelineError):
    """Raised when caller input is invalid."""

    def __init__(self, message: str):
        super().__init__(message, status_code=400)


class ConfigurationError(NotificationPipelineError):
    """Raised when runtime configuration or infrastructure is unavailable."""

    def __init__(self, message: str):
        super().__init__(message, status_code=500)


class NotFoundError(NotificationPipelineError):
    """Raised when requested data is not found."""

    def __init__(self, message: str):
        super().__init__(message, status_code=404)
