from __future__ import annotations

import uuid
from typing import Any, Callable

from sqlalchemy import select

from src.api.schemas import InboundMessageCanonical
from src.core.database import AsyncSessionLocal
from src.core.ws_manager import manager
from src.models.audit_log import AuditLog
from src.models.inbound import (
    DetectionMethod,
    InboundChannel,
    InboundIntent,
    InboundMessageParsed,
    InboundMessageRaw,
    InboundStatus,
    IntentCategory,
)
from src.services.inbound_parser import InboundParserService, PARSER_VERSION
from src.services.intent_engine import IntentEngineService

from .exceptions import ConfigurationError, NotFoundError, NotificationPipelineError, ValidationError
from .notifications import _map_exception, _run_sync, _session_scope

SessionFactory = Callable[[], Any]


def _coerce_model(model_cls, value: Any):
    if value is None:
        return None
    if isinstance(value, model_cls):
        return value
    return model_cls.model_validate(value)


def _get_inbound_task():
    from src.tasks.inbound_tasks import process_inbound_message

    return process_inbound_message


def _normalize_inbound_message(
    inbound_message: InboundMessageCanonical | dict[str, Any],
) -> InboundMessageCanonical:
    return _coerce_model(InboundMessageCanonical, inbound_message)


def _serialize_intent(intent_record: InboundIntent | None) -> dict[str, Any] | None:
    if not intent_record:
        return None
    return {
        "id": str(intent_record.id),
        "intent": intent_record.intent.value
        if hasattr(intent_record.intent, "value")
        else str(intent_record.intent),
        "confidence": float(intent_record.confidence),
        "detection_method": intent_record.detection_method.value
        if hasattr(intent_record.detection_method, "value")
        else str(intent_record.detection_method),
        "rationale": intent_record.rationale,
        "needs_review": bool(intent_record.needs_review),
        "created_at": intent_record.created_at.isoformat() if intent_record.created_at else None,
    }


def _serialize_parsed(parsed_record: InboundMessageParsed | None) -> dict[str, Any] | None:
    if not parsed_record:
        return None
    return {
        "id": str(parsed_record.id),
        "parsed_content": parsed_record.parsed_content,
        "parser_version": parsed_record.parser_version,
        "status": parsed_record.status.value
        if hasattr(parsed_record.status, "value")
        else str(parsed_record.status),
        "failure_reason": parsed_record.failure_reason,
        "metadata_json": parsed_record.metadata_json,
        "reference_id": parsed_record.reference_id,
        "created_at": parsed_record.created_at.isoformat() if parsed_record.created_at else None,
        "updated_at": parsed_record.updated_at.isoformat() if parsed_record.updated_at else None,
    }


def _serialize_raw(raw_record: InboundMessageRaw) -> dict[str, Any]:
    return {
        "id": str(raw_record.id),
        "tenant_id": raw_record.tenant_id,
        "candidate_id": raw_record.candidate_id,
        "sender_address": raw_record.sender_address,
        "channel": raw_record.channel.value
        if hasattr(raw_record.channel, "value")
        else str(raw_record.channel),
        "provider_message_id": raw_record.provider_message_id,
        "raw_payload": raw_record.raw_payload,
        "owner_id": str(raw_record.owner_id) if raw_record.owner_id else None,
        "retention_date": raw_record.retention_date.isoformat() if raw_record.retention_date else None,
        "created_at": raw_record.created_at.isoformat() if raw_record.created_at else None,
        "updated_at": raw_record.updated_at.isoformat() if raw_record.updated_at else None,
    }


def _serialize_inbound_result(
    raw_record: InboundMessageRaw,
    parsed_record: InboundMessageParsed | None,
    intent_record: InboundIntent | None,
    *,
    queued: bool = False,
) -> dict[str, Any]:
    return {
        "status": "queued" if queued else "processed",
        "raw_message": _serialize_raw(raw_record),
        "parsed_message": _serialize_parsed(parsed_record),
        "intent": _serialize_intent(intent_record),
    }


async def _persist_inbound_message(
    session: Any,
    inbound_message: InboundMessageCanonical,
) -> InboundMessageRaw:
    inbound_raw = InboundMessageRaw(
        tenant_id=inbound_message.tenant_id,
        candidate_id=inbound_message.candidate_id,
        sender_address=inbound_message.sender_address,
        channel=inbound_message.channel,
        provider_message_id=inbound_message.provider_message_id,
        raw_payload=inbound_message.raw_payload,
        owner_id=inbound_message.owner_id,
        retention_date=inbound_message.retention_date,
    )
    session.add(inbound_raw)
    await session.flush()
    return inbound_raw


async def _mark_inbound_failure(
    session: Any,
    inbound_message_id: str | uuid.UUID,
    error_message: str,
) -> None:
    query = select(InboundMessageParsed).where(
        InboundMessageParsed.raw_message_id == inbound_message_id
    )
    result = await session.execute(query)
    parsed_msg = result.scalar_one_or_none()
    if not parsed_msg:
        parsed_msg = InboundMessageParsed(
            raw_message_id=inbound_message_id,
            parser_version=PARSER_VERSION,
        )
        session.add(parsed_msg)

    parsed_msg.status = InboundStatus.FAILED
    parsed_msg.failure_reason = error_message
    await session.flush()


async def process_inbound_record_with_session(
    session: Any,
    inbound_message_id: str,
    *,
    broadcast: bool = False,
) -> dict[str, Any]:
    try:
        inbound_uuid = uuid.UUID(str(inbound_message_id))
    except ValueError as exc:
        raise ValidationError("Invalid inbound message ID format") from exc

    query = select(InboundMessageRaw).where(InboundMessageRaw.id == inbound_uuid)
    result = await session.execute(query)
    inbound_msg = result.scalar_one_or_none()

    if not inbound_msg:
        raise NotFoundError("Inbound message not found")

    query_parsed = select(InboundMessageParsed).where(
        InboundMessageParsed.raw_message_id == inbound_uuid
    )
    result_parsed = await session.execute(query_parsed)
    parsed_msg = result_parsed.scalar_one_or_none()

    if parsed_msg and parsed_msg.status != InboundStatus.FAILED and parsed_msg.intent:
        return _serialize_inbound_result(inbound_msg, parsed_msg, parsed_msg.intent)

    if not parsed_msg:
        parsed_msg = InboundMessageParsed(
            raw_message_id=inbound_msg.id,
            status=InboundStatus.RECEIVED,
            parser_version=PARSER_VERSION,
            reference_id=(inbound_msg.raw_payload or {}).get("metadata", {}).get("in_reply_to"),
        )
        session.add(parsed_msg)
        await session.flush()

    parser = InboundParserService()
    parsed_text = parser.parse(inbound_msg)
    parsed_msg.parsed_content = parsed_text
    parsed_msg.status = InboundStatus.PARSED
    await session.flush()

    intent_engine = IntentEngineService(session)
    intent_record = await intent_engine.detect_intent(parsed_msg, inbound_msg)
    parsed_msg.status = InboundStatus.INTENT_DETECTED
    await session.flush()

    audit_entry = AuditLog(
        event_type="inbound_message_processed",
        user_id=str(inbound_msg.owner_id) if inbound_msg.owner_id else "system",
        resource_type="inbound_message",
        resource_id=str(inbound_msg.id),
        action="process",
        details={
            "channel": inbound_msg.channel.value
            if hasattr(inbound_msg.channel, "value")
            else str(inbound_msg.channel),
            "sender": inbound_msg.sender_address,
            "intent": intent_record.intent.value if intent_record else "unknown",
            "confidence": intent_record.confidence if intent_record else 0.0,
        },
    )
    session.add(audit_entry)
    await session.flush()

    if broadcast:
        await manager.publish_to_tenant(
            inbound_msg.tenant_id,
            {
                "event": "inbound_intent_detected",
                "tenant_id": inbound_msg.tenant_id,
                "owner_id": str(inbound_msg.owner_id) if inbound_msg.owner_id else None,
                "message_id": str(inbound_msg.id),
                "message": {
                    "id": str(inbound_msg.id),
                    "timestamp": inbound_msg.created_at.isoformat() if inbound_msg.created_at else None,
                    "sender_address": inbound_msg.sender_address,
                    "channel": inbound_msg.channel.value if hasattr(inbound_msg.channel, "value") else str(inbound_msg.channel),
                    "content": parsed_msg.parsed_content,
                    "status": parsed_msg.status.value if hasattr(parsed_msg.status, "value") else str(parsed_msg.status),
                    "ai_intent": intent_record.intent.value if intent_record else "unknown",
                    "ai_confidence": float(intent_record.confidence) if intent_record else 0.0,
                    "ai_rationale": intent_record.rationale if intent_record else None,
                },
            },
        )

    return _serialize_inbound_result(inbound_msg, parsed_msg, intent_record)


async def process_inbound_reply_async(
    inbound_message: InboundMessageCanonical | dict[str, Any],
    *,
    enqueue: bool = False,
    broadcast: bool = False,
    session: Any | None = None,
    session_factory: SessionFactory | None = None,
) -> dict[str, Any]:
    try:
        normalized_message = _normalize_inbound_message(inbound_message)
        if session is not None:
            raw_record = await _persist_inbound_message(session, normalized_message)
            if enqueue:
                _get_inbound_task().delay(str(raw_record.id))
                return _serialize_inbound_result(raw_record, None, None, queued=True)
            return await process_inbound_record_with_session(
                session,
                str(raw_record.id),
                broadcast=broadcast,
            )

        async with _session_scope(session_factory) as managed_session:
            raw_record = await _persist_inbound_message(managed_session, normalized_message)
            if enqueue:
                _get_inbound_task().delay(str(raw_record.id))
                return _serialize_inbound_result(raw_record, None, None, queued=True)
            return await process_inbound_record_with_session(
                managed_session,
                str(raw_record.id),
                broadcast=broadcast,
            )
    except Exception as exc:
        raise _map_exception(exc) from exc


async def detect_reply_intent_async(
    inbound_message: InboundMessageCanonical | dict[str, Any],
    *,
    broadcast: bool = False,
    session: Any | None = None,
    session_factory: SessionFactory | None = None,
) -> dict[str, Any]:
    result = await process_inbound_reply_async(
        inbound_message,
        enqueue=False,
        broadcast=broadcast,
        session=session,
        session_factory=session_factory,
    )
    return result.get("intent") or {
        "intent": IntentCategory.UNKNOWN.value,
        "confidence": 0.0,
        "detection_method": DetectionMethod.MANUAL.value,
        "rationale": "No intent record created",
        "needs_review": True,
    }


async def get_inbound_conversation_async(
    tenant_id: str,
    *,
    sender_address: str | None = None,
    candidate_id: str | None = None,
    reference_id: str | None = None,
    limit: int = 50,
    session: Any | None = None,
    session_factory: SessionFactory | None = None,
) -> dict[str, Any]:
    if not tenant_id:
        raise ValidationError("tenant_id is required")
    if not any([sender_address, candidate_id, reference_id]):
        raise ValidationError(
            "Provide at least one of sender_address, candidate_id, or reference_id"
        )

    async def _load_conversation(active_session: Any) -> dict[str, Any]:
        query = (
            select(InboundMessageRaw, InboundMessageParsed, InboundIntent)
            .outerjoin(InboundMessageParsed, InboundMessageParsed.raw_message_id == InboundMessageRaw.id)
            .outerjoin(InboundIntent, InboundIntent.parsed_message_id == InboundMessageParsed.id)
            .where(InboundMessageRaw.tenant_id == tenant_id)
            .order_by(InboundMessageRaw.created_at.desc())
            .limit(limit)
        )

        if sender_address:
            query = query.where(InboundMessageRaw.sender_address == sender_address)
        if candidate_id:
            query = query.where(InboundMessageRaw.candidate_id == candidate_id)
        if reference_id:
            query = query.where(InboundMessageParsed.reference_id == reference_id)

        result = await active_session.execute(query)
        rows = result.all()
        return {
            "tenant_id": tenant_id,
            "sender_address": sender_address,
            "candidate_id": candidate_id,
            "reference_id": reference_id,
            "messages": [
                _serialize_inbound_result(raw_record, parsed_record, intent_record)
                for raw_record, parsed_record, intent_record in rows
            ],
        }

    try:
        if session is not None:
            return await _load_conversation(session)
        async with _session_scope(session_factory) as managed_session:
            return await _load_conversation(managed_session)
    except Exception as exc:
        raise _map_exception(exc) from exc


def process_inbound_reply(
    inbound_message: InboundMessageCanonical | dict[str, Any],
    *,
    enqueue: bool = False,
    broadcast: bool = False,
    session: Any | None = None,
    session_factory: SessionFactory | None = None,
) -> dict[str, Any]:
    return _run_sync(
        process_inbound_reply_async(
            inbound_message,
            enqueue=enqueue,
            broadcast=broadcast,
            session=session,
            session_factory=session_factory,
        )
    )


def detect_reply_intent(
    inbound_message: InboundMessageCanonical | dict[str, Any],
    *,
    broadcast: bool = False,
    session: Any | None = None,
    session_factory: SessionFactory | None = None,
) -> dict[str, Any]:
    return _run_sync(
        detect_reply_intent_async(
            inbound_message,
            broadcast=broadcast,
            session=session,
            session_factory=session_factory,
        )
    )


def get_inbound_conversation(
    tenant_id: str,
    *,
    sender_address: str | None = None,
    candidate_id: str | None = None,
    reference_id: str | None = None,
    limit: int = 50,
    session: Any | None = None,
    session_factory: SessionFactory | None = None,
) -> dict[str, Any]:
    return _run_sync(
        get_inbound_conversation_async(
            tenant_id,
            sender_address=sender_address,
            candidate_id=candidate_id,
            reference_id=reference_id,
            limit=limit,
            session=session,
            session_factory=session_factory,
        )
    )
