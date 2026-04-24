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
    Async logic to run the actual pipeline
    """
    from src.core import async_session_maker
    from sqlalchemy import select
    from src.models.inbound import InboundMessage, InboundStatus
    from src.services.inbound_parser import InboundParserService
    from src.services.intent_engine import IntentEngineService

    logger.info(f"Starting inbound processing for message {inbound_message_id}")

    async with async_session_maker() as db:
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
        await db.commit()

        # 2. Intent Detection
        intent_engine = IntentEngineService(db)
        intent_record = await intent_engine.detect_intent(inbound_msg)
        
        inbound_msg.status = InboundStatus.INTENT_DETECTED
        await db.commit()

        logger.info(f"Message {inbound_message_id} processed. Detected intent: {intent_record.intent.value}")
        
        # NOTE: Pausing here per Epic 5 adjustments. Dispatch to downstream workflow omitted.
