from celery import shared_task
import asyncio
import logging

logger = logging.getLogger(__name__)

@shared_task(name="inbound.process_inbound_message")
def process_inbound_message(inbound_message_id: str):
    """
    Celery task to orchestrate parsing and intent detection for an inbound message.
    """
    # Wrap async execution
    loop = asyncio.get_event_loop()
    if loop.is_running():
        # Handle if already running in an async context, though Celery workers usually aren't async
        asyncio.ensure_future(run_inbound_pipeline(inbound_message_id))
    else:
        loop.run_until_complete(run_inbound_pipeline(inbound_message_id))


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
    from src.models.inbound import InboundMessage, InboundStatus
    from src.models.audit_log import AuditLog
    from src.services.inbound_parser import InboundParserService
    from src.services.intent_engine import IntentEngineService
    from datetime import datetime

    logger.info(f"Starting inbound processing for message {inbound_message_id}")

    async with AsyncSessionLocal() as db:
        try:
            query = select(InboundMessage).where(InboundMessage.id == inbound_message_id)
            result = await db.execute(query)
            inbound_msg = result.scalar_one_or_none()

            if not inbound_msg:
                logger.error(f"Inbound message {inbound_message_id} not found.")
                return

            if inbound_msg.status != InboundStatus.RECEIVED:
                logger.info(f"Message {inbound_message_id} already processed (status: {inbound_msg.status})")
                return

            # 1. Parsing
            parser = InboundParserService()
            parsed_text = parser.parse(inbound_msg)
            inbound_msg.parsed_content = parsed_text
            inbound_msg.status = InboundStatus.PARSED
            await db.flush()

            # 2. Intent Detection
            intent_engine = IntentEngineService(db)
            intent_record = await intent_engine.detect_intent(inbound_msg)
            
            inbound_msg.status = InboundStatus.INTENT_DETECTED
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

        except Exception as e:
            logger.error(f"Error in run_inbound_pipeline: {e}", exc_info=True)
            await db.rollback()
            # Mark as failed
            async with AsyncSessionLocal() as db_fail:
                await db_fail.execute(
                    update(InboundMessage)
                    .where(InboundMessage.id == inbound_message_id)
                    .values(status=InboundStatus.FAILED)
                )
                await db_fail.commit()
