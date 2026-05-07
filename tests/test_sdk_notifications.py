from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
import importlib.util
import sys
from types import SimpleNamespace
import types

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["DEBUG"] = "true"
fake_sync_team = types.ModuleType("src.agents.sync_team")
fake_sync_team.get_notification_team = lambda: None
sys.modules.setdefault("src.agents.sync_team", fake_sync_team)

from src.api.schemas import (
    BatchMultiChannelNotificationResponse,
    BatchNotificationResponse,
    NotificationResponse,
    NotificationStatus,
    NotificationStatusResponse,
)
from src.sdk.exceptions import ConfigurationError, ValidationError
from src.sdk.notifications import (
    get_notification_status,
    get_notification_status_async,
    send_batch_multichannel_notification_pipeline_async,
    send_batch_notification_pipeline_async,
    send_notification_pipeline,
    send_notification_pipeline_async,
)

router_path = Path(__file__).resolve().parents[1] / "src" / "api" / "routers" / "notifications.py"
router_spec = importlib.util.spec_from_file_location("sdk_notifications_router_test", router_path)
notifications_router = importlib.util.module_from_spec(router_spec)
assert router_spec is not None and router_spec.loader is not None
router_spec.loader.exec_module(notifications_router)


class FakeSession:
    def __init__(self):
        self.commit_called = 0
        self.rollback_called = 0
        self.close_called = 0

    async def commit(self):
        self.commit_called += 1

    async def rollback(self):
        self.rollback_called += 1

    async def close(self):
        self.close_called += 1


@pytest.mark.asyncio
async def test_send_notification_pipeline_async_success(monkeypatch):
    captured = {}

    class FakeService:
        def __init__(self, db):
            self.db = db

        async def send_notification(self, tenant_id, request, owner_id=None):
            captured["tenant_id"] = tenant_id
            captured["user_id"] = request.recipient.user_id
            captured["owner_id"] = owner_id
            return NotificationResponse(
                notification_id="notif-123",
                status=NotificationStatus.QUEUED,
                channels={},
                estimated_delivery=None,
                created_at=datetime.utcnow(),
            )

    monkeypatch.setattr("src.sdk.notifications._get_notification_service_cls", lambda: FakeService)

    result = await send_notification_pipeline_async(
        "tenant_123",
        {"user_id": "user_1", "email": "user@example.com"},
        {
            "type": "order_update",
            "priority": "high",
            "channels": ["email"],
            "subject": "Hi",
            "body": "Hello",
        },
        owner_id="owner-1",
        session_factory=FakeSession,
    )

    assert result.notification_id == "notif-123"
    assert captured == {
        "tenant_id": "tenant_123",
        "user_id": "user_1",
        "owner_id": "owner-1",
    }


@pytest.mark.asyncio
async def test_send_notification_pipeline_async_validation_error():
    with pytest.raises(ValidationError) as exc_info:
        await send_notification_pipeline_async(
            "tenant_123",
            {"email": "user@example.com"},
            {
                "type": "order_update",
                "priority": "high",
                "channels": ["email"],
                "subject": "Hi",
                "body": "Hello",
            },
            session_factory=FakeSession,
        )

    assert "user_id" in str(exc_info.value)


@pytest.mark.asyncio
async def test_send_notification_pipeline_async_whatsapp_requires_template(monkeypatch):
    class FakeService:
        def __init__(self, db):
            self.db = db

        async def send_notification(self, tenant_id, request, owner_id=None):
            raise HTTPException(
                status_code=400,
                detail="template_id is required when requesting whatsapp channel.",
            )

    monkeypatch.setattr("src.sdk.notifications._get_notification_service_cls", lambda: FakeService)

    with pytest.raises(ValidationError) as exc_info:
        await send_notification_pipeline_async(
            "tenant_123",
            {"user_id": "user_1", "phone": "+14155550123"},
            {
                "type": "order_update",
                "priority": "high",
                "channels": ["whatsapp"],
                "body": "Hello",
            },
            session_factory=FakeSession,
        )

    assert "template_id" in str(exc_info.value)


@pytest.mark.asyncio
async def test_send_batch_notification_pipeline_async_success(monkeypatch):
    class FakeService:
        def __init__(self, db):
            self.db = db

        async def send_batch_notifications(self, tenant_id, request, owner_id=None):
            return BatchNotificationResponse(
                batch_id="batch-123",
                status="processing",
                total_recipients=len(request.recipients),
                estimated_completion=None,
            )

    monkeypatch.setattr("src.sdk.notifications._get_notification_service_cls", lambda: FakeService)

    result = await send_batch_notification_pipeline_async(
        "tenant_123",
        {
            "channel": "email",
            "body": "Hello",
            "recipients": [{"user_id": "u1", "email": "u1@example.com"}],
        },
        session_factory=FakeSession,
    )

    assert result.batch_id == "batch-123"
    assert result.total_recipients == 1


@pytest.mark.asyncio
async def test_send_batch_multichannel_notification_pipeline_async_success(monkeypatch):
    class FakeService:
        def __init__(self, db):
            self.db = db

        async def send_batch_notifications_multichannel(self, tenant_id, request, owner_id=None):
            return BatchMultiChannelNotificationResponse(
                batch_id="batch-mc-123",
                status="processing",
                total_recipients=len(request.recipients),
                total_notifications=1,
                total_channel_records=2,
                channels=["email", "sms"],
                estimated_completion=None,
            )

    monkeypatch.setattr("src.sdk.notifications._get_notification_service_cls", lambda: FakeService)

    result = await send_batch_multichannel_notification_pipeline_async(
        "tenant_123",
        {
            "channels": ["email", "sms"],
            "body": "Hello",
            "recipients": [{"user_id": "u1", "email": "u1@example.com", "phone": "+14155550123"}],
        },
        session_factory=FakeSession,
    )

    assert result.batch_id == "batch-mc-123"
    assert result.channels == ["email", "sms"]


@pytest.mark.asyncio
async def test_get_notification_status_async_success(monkeypatch):
    expected = NotificationStatusResponse(
        notification_id="00000000-0000-0000-0000-000000000001",
        user_id="user_1",
        type="order_update",
        priority="high",
        status="queued",
        channels=[],
        attempts=0,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    async def fake_get_status(session, tenant_id, notification_id):
        return expected

    monkeypatch.setattr("src.sdk.notifications._get_notification_status_with_session", fake_get_status)

    result = await get_notification_status_async(
        "tenant_123",
        "00000000-0000-0000-0000-000000000001",
        session_factory=FakeSession,
    )

    assert result == expected


def test_send_notification_pipeline_sync_consumer_wrapper(monkeypatch):
    expected = NotificationResponse(
        notification_id="notif-sync-123",
        status=NotificationStatus.QUEUED,
        channels={},
        estimated_delivery=None,
        created_at=datetime.utcnow(),
    )

    async def fake_async(*args, **kwargs):
        return expected

    monkeypatch.setattr("src.sdk.notifications.send_notification_pipeline_async", fake_async)

    result = send_notification_pipeline(
        "tenant_123",
        {"user_id": "user_1", "email": "user@example.com"},
        {
            "type": "order_update",
            "priority": "high",
            "channels": ["email"],
            "subject": "Hi",
            "body": "Hello",
        },
    )

    assert result == expected


def test_get_notification_status_sync_consumer_wrapper(monkeypatch):
    expected = NotificationStatusResponse(
        notification_id="00000000-0000-0000-0000-000000000001",
        user_id="user_1",
        type="order_update",
        priority="high",
        status="queued",
        channels=[],
        attempts=0,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    async def fake_async(*args, **kwargs):
        return expected

    monkeypatch.setattr("src.sdk.notifications.get_notification_status_async", fake_async)

    result = get_notification_status(
        "tenant_123",
        "00000000-0000-0000-0000-000000000001",
    )

    assert result == expected


def test_invalid_db_configuration_raises_configuration_error():
    def broken_session_factory():
        raise RuntimeError("bad supabase connection string")

    with pytest.raises(ConfigurationError) as exc_info:
        send_notification_pipeline(
            "tenant_123",
            {"user_id": "user_1", "email": "user@example.com"},
            {
                "type": "order_update",
                "priority": "high",
                "channels": ["email"],
                "subject": "Hi",
                "body": "Hello",
            },
            session_factory=broken_session_factory,
        )

    assert "Unable to create database session" in str(exc_info.value)


@pytest.mark.asyncio
async def test_router_send_notification_delegates_to_shared_facade(monkeypatch):
    expected = NotificationResponse(
        notification_id="notif-router-123",
        status=NotificationStatus.QUEUED,
        channels={},
        estimated_delivery=None,
        created_at=datetime.utcnow(),
    )
    captured = {}

    async def fake_send(tenant_id, recipient, notification, options=None, **kwargs):
        captured["tenant_id"] = tenant_id
        captured["user_id"] = recipient.user_id
        captured["owner_id"] = kwargs.get("owner_id")
        return expected

    monkeypatch.setattr(notifications_router, "send_notification_pipeline_async", fake_send)

    tenant = SimpleNamespace(id="tenant_123", current_user_id="owner-1")
    request = SimpleNamespace(
        recipient=SimpleNamespace(user_id="user_1"),
        notification=SimpleNamespace(),
        options=None,
    )

    result = await notifications_router.send_notification(
        request=request,
        db=FakeSession(),
        tenant=tenant,
    )

    assert result == expected
    assert captured == {
        "tenant_id": "tenant_123",
        "user_id": "user_1",
        "owner_id": "owner-1",
    }
