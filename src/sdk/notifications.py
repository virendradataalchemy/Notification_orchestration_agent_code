from __future__ import annotations

import asyncio
import threading
import uuid
from contextlib import asynccontextmanager
from typing import Any, Callable

from fastapi import HTTPException
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.api.schemas import (
    BatchNotificationRequest,
    BatchNotificationResponse,
    BatchMultiChannelNotificationRequest,
    BatchMultiChannelNotificationResponse,
    NotificationData,
    NotificationOptions,
    NotificationResponse,
    NotificationStatusResponse,
    RecipientInfo,
    SendNotificationRequest,
)
from src.core.database import AsyncSessionLocal
from src.models import Notification

from .exceptions import ConfigurationError, NotFoundError, NotificationPipelineError, ValidationError

SessionFactory = Callable[[], Any]


def _get_notification_service_cls():
    from src.services.notification_service import NotificationService

    return NotificationService


def _coerce_model(model_cls, value: Any):
    if value is None:
        return None
    if isinstance(value, model_cls):
        return value
    return model_cls.model_validate(value)


def _normalize_send_request(
    recipient: RecipientInfo | dict[str, Any],
    notification: NotificationData | dict[str, Any],
    options: NotificationOptions | dict[str, Any] | None = None,
) -> SendNotificationRequest:
    return SendNotificationRequest.model_validate(
        {
            "recipient": _coerce_model(RecipientInfo, recipient).model_dump(),
            "notification": _coerce_model(NotificationData, notification).model_dump(),
            "options": _coerce_model(NotificationOptions, options).model_dump() if options else None,
        }
    )


def _normalize_batch_request(
    request: BatchNotificationRequest | dict[str, Any],
) -> BatchNotificationRequest:
    return _coerce_model(BatchNotificationRequest, request)


def _normalize_batch_multichannel_request(
    request: BatchMultiChannelNotificationRequest | dict[str, Any],
) -> BatchMultiChannelNotificationRequest:
    return _coerce_model(BatchMultiChannelNotificationRequest, request)


def _map_exception(exc: Exception) -> NotificationPipelineError:
    if isinstance(exc, NotificationPipelineError):
        return exc
    if isinstance(exc, PydanticValidationError):
        return ValidationError(str(exc))
    if isinstance(exc, HTTPException):
        status_code = exc.status_code or 500
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        if status_code == 404:
            return NotFoundError(detail)
        if status_code in {400, 401, 403, 409, 422, 429}:
            return ValidationError(detail)
        return ConfigurationError(detail)
    return NotificationPipelineError(str(exc), status_code=500)


@asynccontextmanager
async def _session_scope(session_factory: SessionFactory | None = None):
    factory = session_factory or AsyncSessionLocal
    try:
        session = factory()
    except Exception as exc:
        raise ConfigurationError(f"Unable to create database session: {exc}") from exc

    async with _existing_session_scope(session):
        yield session


@asynccontextmanager
async def _existing_session_scope(session: Any):
    try:
        yield session
        await session.commit()
    except NotificationPipelineError:
        await session.rollback()
        raise
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


def _serialize_notification_status(notification: Notification) -> NotificationStatusResponse:
    channels = [
        {
            "channel": channel.channel,
            "provider": channel.provider,
            "message_id": channel.message_id,
            "status": channel.status.value,
            "delivered_at": channel.delivered_at,
            "opened_at": channel.opened_at,
            "clicked_at": channel.clicked_at,
        }
        for channel in notification.channels
    ]

    return NotificationStatusResponse(
        notification_id=str(notification.id),
        user_id=notification.user_id,
        type=notification.type,
        priority=notification.priority,
        status=notification.status,
        channels=channels,
        attempts=sum(c.attempts for c in notification.channels),
        created_at=notification.created_at,
        updated_at=notification.updated_at,
    )


async def _get_notification_status_with_session(
    session: Any, tenant_id: str, notification_id: str
) -> NotificationStatusResponse:
    try:
        notification_uuid = uuid.UUID(notification_id)
    except ValueError as exc:
        raise ValidationError("Invalid notification ID format") from exc

    query = select(Notification).where(
        Notification.id == notification_uuid,
        Notification.tenant_id == tenant_id,
    ).options(selectinload(Notification.channels))
    result = await session.execute(query)
    notification = result.scalar_one_or_none()

    if not notification:
        raise NotFoundError("Notification not found")

    return _serialize_notification_status(notification)


async def send_notification_pipeline_async(
    tenant_id: str,
    recipient: RecipientInfo | dict[str, Any],
    notification: NotificationData | dict[str, Any],
    options: NotificationOptions | dict[str, Any] | None = None,
    *,
    owner_id: str | None = None,
    session: Any | None = None,
    session_factory: SessionFactory | None = None,
) -> NotificationResponse:
    if not tenant_id:
        raise ValidationError("tenant_id is required")

    try:
        request = _normalize_send_request(recipient, notification, options)
        if session is not None:
            service = _get_notification_service_cls()(session)
            return await service.send_notification(tenant_id, request, owner_id=owner_id)
        async with _session_scope(session_factory) as managed_session:
            service = _get_notification_service_cls()(managed_session)
            return await service.send_notification(tenant_id, request, owner_id=owner_id)
    except Exception as exc:
        raise _map_exception(exc) from exc


async def send_batch_notification_pipeline_async(
    tenant_id: str,
    request: BatchNotificationRequest | dict[str, Any],
    *,
    owner_id: str | None = None,
    session: Any | None = None,
    session_factory: SessionFactory | None = None,
) -> BatchNotificationResponse:
    if not tenant_id:
        raise ValidationError("tenant_id is required")

    try:
        normalized_request = _normalize_batch_request(request)
        if session is not None:
            service = _get_notification_service_cls()(session)
            return await service.send_batch_notifications(
                tenant_id, normalized_request, owner_id=owner_id
            )
        async with _session_scope(session_factory) as managed_session:
            service = _get_notification_service_cls()(managed_session)
            return await service.send_batch_notifications(
                tenant_id, normalized_request, owner_id=owner_id
            )
    except Exception as exc:
        raise _map_exception(exc) from exc


async def send_batch_multichannel_notification_pipeline_async(
    tenant_id: str,
    request: BatchMultiChannelNotificationRequest | dict[str, Any],
    *,
    owner_id: str | None = None,
    session: Any | None = None,
    session_factory: SessionFactory | None = None,
) -> BatchMultiChannelNotificationResponse:
    if not tenant_id:
        raise ValidationError("tenant_id is required")

    try:
        normalized_request = _normalize_batch_multichannel_request(request)
        if session is not None:
            service = _get_notification_service_cls()(session)
            return await service.send_batch_notifications_multichannel(
                tenant_id, normalized_request, owner_id=owner_id
            )
        async with _session_scope(session_factory) as managed_session:
            service = _get_notification_service_cls()(managed_session)
            return await service.send_batch_notifications_multichannel(
                tenant_id, normalized_request, owner_id=owner_id
            )
    except Exception as exc:
        raise _map_exception(exc) from exc


async def get_notification_status_async(
    tenant_id: str,
    notification_id: str,
    *,
    session: Any | None = None,
    session_factory: SessionFactory | None = None,
) -> NotificationStatusResponse:
    if not tenant_id:
        raise ValidationError("tenant_id is required")

    try:
        if session is not None:
            return await _get_notification_status_with_session(session, tenant_id, notification_id)
        async with _session_scope(session_factory) as managed_session:
            return await _get_notification_status_with_session(
                managed_session, tenant_id, notification_id
            )
    except Exception as exc:
        raise _map_exception(exc) from exc


def _run_sync(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result: dict[str, Any] = {}
    error: dict[str, BaseException] = {}

    def runner():
        try:
            result["value"] = asyncio.run(coro)
        except BaseException as exc:  # pragma: no cover - defensive bridge
            error["value"] = exc

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join()

    if "value" in error:
        raise error["value"]
    return result.get("value")


def send_notification_pipeline(
    tenant_id: str,
    recipient: RecipientInfo | dict[str, Any],
    notification: NotificationData | dict[str, Any],
    options: NotificationOptions | dict[str, Any] | None = None,
    *,
    owner_id: str | None = None,
    session: Any | None = None,
    session_factory: SessionFactory | None = None,
) -> NotificationResponse:
    return _run_sync(
        send_notification_pipeline_async(
            tenant_id,
            recipient,
            notification,
            options,
            owner_id=owner_id,
            session=session,
            session_factory=session_factory,
        )
    )


def send_batch_notification_pipeline(
    tenant_id: str,
    request: BatchNotificationRequest | dict[str, Any],
    *,
    owner_id: str | None = None,
    session: Any | None = None,
    session_factory: SessionFactory | None = None,
) -> BatchNotificationResponse:
    return _run_sync(
        send_batch_notification_pipeline_async(
            tenant_id,
            request,
            owner_id=owner_id,
            session=session,
            session_factory=session_factory,
        )
    )


def send_batch_multichannel_notification_pipeline(
    tenant_id: str,
    request: BatchMultiChannelNotificationRequest | dict[str, Any],
    *,
    owner_id: str | None = None,
    session: Any | None = None,
    session_factory: SessionFactory | None = None,
) -> BatchMultiChannelNotificationResponse:
    return _run_sync(
        send_batch_multichannel_notification_pipeline_async(
            tenant_id,
            request,
            owner_id=owner_id,
            session=session,
            session_factory=session_factory,
        )
    )


def get_notification_status(
    tenant_id: str,
    notification_id: str,
    *,
    session: Any | None = None,
    session_factory: SessionFactory | None = None,
) -> NotificationStatusResponse:
    return _run_sync(
        get_notification_status_async(
            tenant_id,
            notification_id,
            session=session,
            session_factory=session_factory,
        )
    )
