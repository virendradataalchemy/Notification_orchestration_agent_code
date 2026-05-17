from celery import shared_task
import asyncio
import logging
from src.celery_app import get_shared_task_loop

logger = logging.getLogger(__name__)

@shared_task(name="inbound.process_inbound_message", bind=True, max_retries=3, default_retry_delay=10)
def process_inbound_message(self, inbound_message_id: str):
    """
    Celery task to orchestrate parsing and intent detection for an inbound message.
    Automatically retries up to 3 times with 10 second delay on failure.
    """
    # Reuse the process-local loop so async DB connections stay attached
    # to the same event loop inside the Celery worker process.
    loop = get_shared_task_loop()
    try:
        asyncio.set_event_loop(loop)
        loop.run_until_complete(run_inbound_pipeline(inbound_message_id))
    except Exception as e:
        logger.error(f"Failed to run inbound pipeline for {inbound_message_id}: {e}")
        # Retry the task
        try:
            raise self.retry(exc=e, countdown=10)
        except self.MaxRetriesExceededError:
            logger.error(f"Max retries exceeded for message {inbound_message_id}")
            asyncio.set_event_loop(loop)
            loop.run_until_complete(mark_message_failed(inbound_message_id, str(e)))


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


@shared_task(name="inbound.retry_stuck_messages")
def retry_stuck_messages():
    """
    Periodic task to find and reprocess stuck inbound messages.
    Runs every 5 minutes to ensure no messages are left unprocessed.
    """
    try:
        loop = get_shared_task_loop()
        loop.run_until_complete(find_and_retry_stuck_messages())
    except Exception as e:
        logger.error(f"Failed to retry stuck messages: {e}")


async def find_and_retry_stuck_messages():
    """
    Find inbound messages that don't have parsed records and retry them.
    Only retries messages older than 2 minutes to avoid race conditions.
    """
    from src.core.database import AsyncSessionLocal
    from sqlalchemy import text
    from datetime import datetime, timedelta
    
    logger.info("Checking for stuck inbound messages...")
    
    async with AsyncSessionLocal() as db:
        # Find messages older than 2 minutes without parsed records
        # or messages that failed due to IO loop issues
        cutoff_time = datetime.utcnow() - timedelta(minutes=2)
        
        result = await db.execute(text("""
            SELECT r.id::text 
            FROM inbound_messages_raw r
            LEFT JOIN inbound_messages_parsed p ON p.raw_message_id = r.id
            WHERE (p.id IS NULL OR p.status = 'FAILED')
            AND r.created_at < :cutoff
            ORDER BY r.created_at ASC
            LIMIT 50
        """), {"cutoff": cutoff_time})
        
        stuck_messages = result.fetchall()
        
        if not stuck_messages:
            logger.info("No stuck messages found")
            return
        
        count = 0
        for row in stuck_messages:
            msg_id = row[0]
            logger.warning(f"Retrying stuck message: {msg_id}")
            # Queue the task
            process_inbound_message.delay(msg_id)
            count += 1
        
        logger.info(f"Queued {count} stuck messages for retry")


async def mark_message_failed(inbound_message_id: str, error: str):
    """Mark an inbound message as permanently failed after max retries."""
    from src.core.database import AsyncSessionLocal
    from src.models.inbound import InboundMessageRaw, InboundMessageParsed, InboundStatus
    from sqlalchemy import select
    from datetime import datetime
    import uuid
    
    async with AsyncSessionLocal() as db:
        try:
            # Add failure metadata to raw msg
            query = select(InboundMessageRaw).where(InboundMessageRaw.id == uuid.UUID(str(inbound_message_id)))
            result = await db.execute(query)
            msg = result.scalar_one_or_none()
            
            if msg:
                # Add failure metadata
                if not getattr(msg, "metadata_json", None):
                    msg.metadata_json = {}
                msg.metadata_json['processing_failed'] = True
                msg.metadata_json['failure_reason'] = error
                msg.metadata_json['failed_at'] = datetime.utcnow().isoformat()
            
            # Also ensure parsed record exists and is marked as FAILED
            query_parsed = select(InboundMessageParsed).where(InboundMessageParsed.raw_message_id == uuid.UUID(str(inbound_message_id)))
            result_parsed = await db.execute(query_parsed)
            parsed_msg = result_parsed.scalar_one_or_none()
            
            if parsed_msg:
                parsed_msg.status = InboundStatus.FAILED
                parsed_msg.failure_reason = f"Max retries exceeded: {error}"
            else:
                parsed_msg = InboundMessageParsed(
                    raw_message_id=uuid.UUID(str(inbound_message_id)),
                    status=InboundStatus.FAILED,
                    failure_reason=f"Max retries exceeded: {error}"
                )
                db.add(parsed_msg)
                
            await db.commit()
            logger.error(f"Marked message {inbound_message_id} as permanently failed")
        except Exception as e:
            logger.error(f"Failed to mark message as failed: {e}")
            await db.rollback()
