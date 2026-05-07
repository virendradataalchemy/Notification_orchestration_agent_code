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
    from src.sdk.inbound import process_inbound_record_with_session, _mark_inbound_failure

    logger.info(f"Starting inbound processing for message {inbound_message_id}")

    async with AsyncSessionLocal() as db:
        try:
            await process_inbound_record_with_session(
                db,
                inbound_message_id,
                broadcast=True,
            )
            await db.commit()
            logger.info(f"Message {inbound_message_id} processed successfully")

        except Exception as e:
            logger.error(f"Error in run_inbound_pipeline: {e}", exc_info=True)
            await db.rollback()
            async with AsyncSessionLocal() as db_fail:
                await _mark_inbound_failure(db_fail, inbound_message_id, str(e))
                await db_fail.commit()
