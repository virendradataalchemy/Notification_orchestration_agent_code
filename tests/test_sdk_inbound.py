from __future__ import annotations

from datetime import UTC, datetime
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import uuid

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["DEBUG"] = "true"

from src.models.inbound import DetectionMethod, InboundChannel, IntentCategory
from src.sdk.exceptions import ValidationError
from src.sdk.inbound import (
    detect_reply_intent,
    detect_reply_intent_async,
    get_inbound_conversation_async,
    process_inbound_reply,
    process_inbound_reply_async,
)
from src.services.intent_engine import IntentEngineService


class FakeSession:
    def __init__(self):
        self.added = []
        self.commit_called = 0
        self.rollback_called = 0
        self.close_called = 0
        self.flush_called = 0

    def add(self, obj):
        if not getattr(obj, "id", None):
            obj.id = "generated-id"
        self.added.append(obj)

    async def flush(self):
        self.flush_called += 1

    async def commit(self):
        self.commit_called += 1

    async def rollback(self):
        self.rollback_called += 1

    async def close(self):
        self.close_called += 1


@pytest.mark.asyncio
async def test_process_inbound_reply_async_immediate_success(monkeypatch):
    raw_record = SimpleNamespace(
        id="raw-123",
        tenant_id="demo_corp",
        candidate_id="candidate-1",
        sender_address="+14155550123",
        channel=InboundChannel.SMS,
        provider_message_id="provider-123",
        raw_payload={"Body": "yes"},
        owner_id=None,
        retention_date=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    expected = {
        "status": "processed",
        "raw_message": {"id": "raw-123"},
        "parsed_message": {"id": "parsed-123"},
        "intent": {"intent": "accept", "confidence": 1.0},
    }

    async def fake_persist(session, inbound_message):
        return raw_record

    async def fake_process(session, inbound_message_id, **kwargs):
        assert inbound_message_id == "raw-123"
        return expected

    monkeypatch.setattr("src.sdk.inbound._persist_inbound_message", fake_persist)
    monkeypatch.setattr("src.sdk.inbound.process_inbound_record_with_session", fake_process)

    result = await process_inbound_reply_async(
        {
            "tenant_id": "demo_corp",
            "channel": "sms",
            "sender_address": "+14155550123",
            "provider_message_id": "provider-123",
            "raw_payload": {"Body": "yes"},
        },
        session_factory=FakeSession,
    )

    assert result == expected


@pytest.mark.asyncio
async def test_process_inbound_reply_async_accepts_chat_channel(monkeypatch):
    raw_record = SimpleNamespace(
        id="raw-chat-123",
        tenant_id="demo_corp",
        candidate_id="candidate-chat-1",
        sender_address="chat_user_001",
        channel=InboundChannel.CHAT,
        provider_message_id="chat-provider-123",
        raw_payload={"message": "Need help with my order"},
        owner_id=None,
        retention_date=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    expected = {
        "status": "processed",
        "raw_message": {"id": "raw-chat-123"},
        "parsed_message": {"id": "parsed-chat-123"},
        "intent": {"intent": "query", "confidence": 0.9},
    }

    async def fake_persist(session, inbound_message):
        assert inbound_message.channel == InboundChannel.CHAT
        return raw_record

    async def fake_process(session, inbound_message_id, **kwargs):
        assert inbound_message_id == "raw-chat-123"
        return expected

    monkeypatch.setattr("src.sdk.inbound._persist_inbound_message", fake_persist)
    monkeypatch.setattr("src.sdk.inbound.process_inbound_record_with_session", fake_process)

    result = await process_inbound_reply_async(
        {
            "tenant_id": "demo_corp",
            "channel": "chat",
            "sender_address": "chat_user_001",
            "provider_message_id": "chat-provider-123",
            "raw_payload": {"message": "Need help with my order"},
        },
        session_factory=FakeSession,
    )

    assert result == expected


@pytest.mark.asyncio
async def test_process_inbound_reply_async_coerces_owner_id_to_uuid(monkeypatch):
    captured = {}
    raw_record = SimpleNamespace(
        id="raw-owner-123",
        tenant_id="demo_corp",
        candidate_id="candidate-owner-1",
        sender_address="+14155550123",
        channel=InboundChannel.SMS,
        provider_message_id="provider-owner-123",
        raw_payload={"Body": "yes"},
        owner_id=None,
        retention_date=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    owner_id = "00000000-0000-0000-0000-000000000123"

    async def fake_persist(session, inbound_message):
        captured["owner_id"] = inbound_message.owner_id
        return raw_record

    async def fake_process(session, inbound_message_id, **kwargs):
        return {
            "status": "processed",
            "raw_message": {"id": "raw-owner-123"},
            "parsed_message": {"id": "parsed-owner-123"},
            "intent": {"intent": "accept", "confidence": 1.0},
        }

    monkeypatch.setattr("src.sdk.inbound._persist_inbound_message", fake_persist)
    monkeypatch.setattr("src.sdk.inbound.process_inbound_record_with_session", fake_process)

    await process_inbound_reply_async(
        {
            "tenant_id": "demo_corp",
            "channel": "sms",
            "sender_address": "+14155550123",
            "provider_message_id": "provider-owner-123",
            "raw_payload": {"Body": "yes"},
            "owner_id": owner_id,
        },
        session_factory=FakeSession,
    )

    assert captured["owner_id"] == uuid.UUID(owner_id)


@pytest.mark.asyncio
async def test_process_inbound_reply_async_enqueue(monkeypatch):
    raw_record = SimpleNamespace(
        id="raw-queued-123",
        tenant_id="demo_corp",
        candidate_id=None,
        sender_address="+14155550123",
        channel=InboundChannel.SMS,
        provider_message_id="provider-123",
        raw_payload={"Body": "yes"},
        owner_id=None,
        retention_date=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    enqueued = {}

    async def fake_persist(session, inbound_message):
        return raw_record

    def fake_delay(message_id):
        enqueued["message_id"] = message_id

    monkeypatch.setattr("src.sdk.inbound._persist_inbound_message", fake_persist)
    monkeypatch.setattr("src.sdk.inbound._get_inbound_task", lambda: SimpleNamespace(delay=fake_delay))

    result = await process_inbound_reply_async(
        {
            "tenant_id": "demo_corp",
            "channel": "sms",
            "sender_address": "+14155550123",
            "provider_message_id": "provider-123",
            "raw_payload": {"Body": "yes"},
        },
        enqueue=True,
        session_factory=FakeSession,
    )

    assert result["status"] == "queued"
    assert enqueued["message_id"] == "raw-queued-123"


@pytest.mark.asyncio
async def test_detect_reply_intent_async_returns_intent_only(monkeypatch):
    async def fake_process(*args, **kwargs):
        return {
            "status": "processed",
            "raw_message": {"id": "raw-123"},
            "parsed_message": {"id": "parsed-123"},
            "intent": {
                "id": "intent-123",
                "intent": "accept",
                "confidence": 1.0,
                "detection_method": "rules",
                "rationale": "Matched Regex Pattern",
                "needs_review": False,
                "created_at": None,
            },
        }

    monkeypatch.setattr("src.sdk.inbound.process_inbound_reply_async", fake_process)

    result = await detect_reply_intent_async(
        {
            "tenant_id": "demo_corp",
            "channel": "sms",
            "sender_address": "+14155550123",
            "provider_message_id": "provider-123",
            "raw_payload": {"Body": "yes"},
        }
    )

    assert result["intent"] == "accept"
    assert result["detection_method"] == "rules"


@pytest.mark.asyncio
async def test_get_inbound_conversation_async_requires_lookup_key():
    with pytest.raises(ValidationError):
        await get_inbound_conversation_async("demo_corp", session_factory=FakeSession)


@pytest.mark.asyncio
async def test_get_inbound_conversation_async_success(monkeypatch):
    class FakeExecuteResult:
        def all(self):
            raw_record = SimpleNamespace(
                id="raw-123",
                tenant_id="demo_corp",
                candidate_id="candidate-1",
                sender_address="user@example.com",
                channel=InboundChannel.EMAIL,
                provider_message_id="provider-123",
                raw_payload={"stripped-text": "Yes, I accept"},
                owner_id=None,
                retention_date=None,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            parsed_record = SimpleNamespace(
                id="parsed-123",
                parsed_content="Yes, I accept",
                parser_version="1.0",
                status="intent_detected",
                failure_reason=None,
                metadata_json=None,
                reference_id="notif-123",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            intent_record = SimpleNamespace(
                id="intent-123",
                intent=IntentCategory.ACCEPT,
                confidence=1.0,
                detection_method=DetectionMethod.RULES,
                rationale="Matched Regex Pattern",
                needs_review=False,
                created_at=datetime.now(UTC),
            )
            return [(raw_record, parsed_record, intent_record)]

    class SessionWithExecute(FakeSession):
        async def execute(self, query):
            return FakeExecuteResult()

    result = await get_inbound_conversation_async(
        "demo_corp",
        sender_address="user@example.com",
        session_factory=SessionWithExecute,
    )

    assert result["tenant_id"] == "demo_corp"
    assert len(result["messages"]) == 1
    assert result["messages"][0]["intent"]["intent"] == "accept"


def test_process_inbound_reply_sync_wrapper(monkeypatch):
    expected = {
        "status": "processed",
        "raw_message": {"id": "raw-123"},
        "parsed_message": {"id": "parsed-123"},
        "intent": {"intent": "accept"},
    }

    async def fake_async(*args, **kwargs):
        return expected

    monkeypatch.setattr("src.sdk.inbound.process_inbound_reply_async", fake_async)

    result = process_inbound_reply(
        {
            "tenant_id": "demo_corp",
            "channel": "sms",
            "sender_address": "+14155550123",
            "provider_message_id": "provider-123",
            "raw_payload": {"Body": "yes"},
        }
    )

    assert result == expected


def test_detect_reply_intent_sync_wrapper(monkeypatch):
    expected = {
        "intent": "accept",
        "confidence": 1.0,
        "detection_method": "rules",
    }

    async def fake_async(*args, **kwargs):
        return expected

    monkeypatch.setattr("src.sdk.inbound.detect_reply_intent_async", fake_async)

    result = detect_reply_intent(
        {
            "tenant_id": "demo_corp",
            "channel": "sms",
            "sender_address": "+14155550123",
            "provider_message_id": "provider-123",
            "raw_payload": {"Body": "yes"},
        }
    )

    assert result == expected


@pytest.mark.asyncio
async def test_intent_engine_prioritizes_query_for_negative_feedback_plus_question(monkeypatch):
    class FakeLLM:
        async def classify_inbound_intent(self, parsed_content):
            return {"intent": "unknown", "confidence": 0.0, "rationale": "not used"}

    monkeypatch.setattr("src.services.intent_engine.BedrockLLMService", lambda: FakeLLM())
    service = IntentEngineService(FakeSession())

    parsed_msg = SimpleNamespace(
        id="parsed-1",
        parsed_content="I don't like your burger. Do you have any other flavours?",
    )
    raw_msg = SimpleNamespace(raw_payload={})

    result = await service.detect_intent(parsed_msg, raw_msg)

    assert result.intent == IntentCategory.QUERY
    assert result.detection_method == DetectionMethod.RULES
    assert result.needs_review is False


@pytest.mark.asyncio
async def test_intent_engine_keeps_request_for_action_question(monkeypatch):
    class FakeLLM:
        async def classify_inbound_intent(self, parsed_content):
            return {"intent": "unknown", "confidence": 0.0, "rationale": "not used"}

    monkeypatch.setattr("src.services.intent_engine.BedrockLLMService", lambda: FakeLLM())
    service = IntentEngineService(FakeSession())

    parsed_msg = SimpleNamespace(
        id="parsed-2",
        parsed_content="Can you reschedule this for tomorrow?",
    )
    raw_msg = SimpleNamespace(raw_payload={})

    result = await service.detect_intent(parsed_msg, raw_msg)

    assert result.intent == IntentCategory.REQUEST
    assert result.detection_method == DetectionMethod.RULES


@pytest.mark.asyncio
async def test_intent_engine_keeps_hard_opt_out_as_reject(monkeypatch):
    class FakeLLM:
        async def classify_inbound_intent(self, parsed_content):
            return {"intent": "unknown", "confidence": 0.0, "rationale": "not used"}

    monkeypatch.setattr("src.services.intent_engine.BedrockLLMService", lambda: FakeLLM())
    service = IntentEngineService(FakeSession())

    parsed_msg = SimpleNamespace(
        id="parsed-3",
        parsed_content="Stop messaging me. Unsubscribe me now.",
    )
    raw_msg = SimpleNamespace(raw_payload={})

    result = await service.detect_intent(parsed_msg, raw_msg)

    assert result.intent == IntentCategory.REJECT
    assert result.detection_method == DetectionMethod.RULES
