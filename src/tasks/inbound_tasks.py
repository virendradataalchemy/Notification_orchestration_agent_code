from celery import shared_task
import asyncio
import logging
from src.celery_app import get_shared_task_loop

logger = logging.getLogger(__name__)

@shared_task(name="inbound.process_inbound_message")
def process_inbound_message(inbound_message_id: str):
    """
    Celery task to orchestrate parsing and intent detection for an inbound message.
    """
    # Wrap async execution
    try:
        loop = get_shared_task_loop()
        loop.run_until_complete(run_inbound_pipeline(inbound_message_id))
    except Exception as e:
        logger.error(f"Failed to run inbound pipeline: {e}")


async def run_inbound_pipeline(inbound_message_id: str):
    """
    Async logic to run the actual pipeline:
    1. Parsing (Cleaning, stripping quotes)
    2. Intent Detection (Rules + LLM)
    3. Audit Logging
    4. Reference matching (linking to outbound)
    """
    from src.core.database import AsyncSessionLocal
    from sqlalchemy import select, update
    from src.models.inbound import InboundMessageRaw, InboundMessageParsed, InboundStatus
    from src.models.audit_log import AuditLog
    from src.services.inbound_parser import InboundParserService, PARSER_VERSION
    from src.services.intent_engine import IntentEngineService
    from datetime import datetime

    logger.info(f"Starting inbound processing for message {inbound_message_id}")

    async with AsyncSessionLocal() as db:
        try:
            query = select(InboundMessageRaw).where(InboundMessageRaw.id == inbound_message_id)
            result = await db.execute(query)
            inbound_msg = result.scalar_one_or_none()

            if not inbound_msg:
                logger.error(f"Inbound message {inbound_message_id} not found.")
                return

            # Check if already parsed
            query_parsed = select(InboundMessageParsed).where(InboundMessageParsed.raw_message_id == inbound_message_id)
            result_parsed = await db.execute(query_parsed)
            parsed_msg = result_parsed.scalar_one_or_none()
            
            if parsed_msg and parsed_msg.status != InboundStatus.FAILED:
                logger.info(f"Message {inbound_message_id} already processed (status: {parsed_msg.status})")
                return

            if not parsed_msg:
                parsed_msg = InboundMessageParsed(
                    raw_message_id=inbound_msg.id,
                    status=InboundStatus.RECEIVED,
                    parser_version=PARSER_VERSION,
                    reference_id=inbound_msg.raw_payload.get("metadata", {}).get("in_reply_to")
                )
                db.add(parsed_msg)

            # 1. Parsing
            parser = InboundParserService()
            parsed_text = parser.parse(inbound_msg)
            parsed_msg.parsed_content = parsed_text
            parsed_msg.status = InboundStatus.PARSED
            await db.flush()

            # 2. Intent Detection
            intent_engine = IntentEngineService(db)
            intent_record = await intent_engine.detect_intent(parsed_msg, inbound_msg)
            
            parsed_msg.status = InboundStatus.INTENT_DETECTED
            await db.flush()

            # 3. Audit Logging
            audit_entry = AuditLog(
                event_type="inbound_message_processed",
                user_id=str(inbound_msg.owner_id) if inbound_msg.owner_id else "system",
                resource_type="inbound_message",
                resource_id=str(inbound_msg.id),
                action="process",
                details={
                    "channel": inbound_msg.channel.value,
                    "sender": inbound_msg.sender_address,
                    "intent": intent_record.intent.value if intent_record else "unknown",
                    "confidence": intent_record.confidence if intent_record else 0.0
                }
            )
            db.add(audit_entry)

            await db.commit()
            logger.info(f"Message {inbound_message_id} processed. Detected intent: {intent_record.intent.value if intent_record else 'N/A'}")
            
            # Notify dashboard via WebSocket that intent is ready
            from src.core.ws_manager import manager
            await manager.broadcast_to_tenant(inbound_msg.tenant_id, {
                "event": "inbound_intent_detected",
                "tenant_id": inbound_msg.tenant_id,
                "owner_id": str(inbound_msg.owner_id) if inbound_msg.owner_id else None,
                "message_id": str(inbound_msg.id),
                "intent": intent_record.intent.value if intent_record else "unknown"
            })

        except Exception as e:
            logger.error(f"Error in run_inbound_pipeline: {e}", exc_info=True)
            await db.rollback()
            # Mark as failed
            async with AsyncSessionLocal() as db_fail:
                # Upsert parsed_msg failure
                query = select(InboundMessageParsed).where(InboundMessageParsed.raw_message_id == inbound_message_id)
                result = await db_fail.execute(query)
                parsed_msg = result.scalar_one_or_none()
                if not parsed_msg:
                    parsed_msg = InboundMessageParsed(
                        raw_message_id=inbound_message_id,
                        parser_version=PARSER_VERSION
                    )
                    db_fail.add(parsed_msg)
                
                parsed_msg.status = InboundStatus.FAILED
                parsed_msg.failure_reason = str(e)
                await db_fail.commit()
