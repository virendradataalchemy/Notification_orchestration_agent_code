from celery import shared_task
import asyncio
import logging

logger = logging.getLogger(__name__)

@shared_task(name="retention.clean_expired_inbound_data")
def clean_expired_inbound_data():
    """
    Celery task to delete expired inbound raw messages to comply with retention policies.
    """
    loop = asyncio.get_event_loop()
    if loop.is_running():
        asyncio.ensure_future(run_retention_cleanup())
    else:
        loop.run_until_complete(run_retention_cleanup())

async def run_retention_cleanup():
    from src.core.database import AsyncSessionLocal
    from sqlalchemy import delete
    from src.models.inbound import InboundMessageRaw
    from datetime import datetime

    logger.info("Running expired inbound data retention cleanup.")
    
    async with AsyncSessionLocal() as db:
        try:
            # Delete any raw message where retention_date is in the past
            now = datetime.utcnow()
            stmt = delete(InboundMessageRaw).where(InboundMessageRaw.retention_date < now)
            result = await db.execute(stmt)
            await db.commit()
            
            deleted_count = result.rowcount
            if deleted_count > 0:
                logger.info(f"Deleted {deleted_count} expired inbound messages.")
            else:
                logger.info("No expired inbound messages found.")
        except Exception as e:
            logger.error(f"Error during retention cleanup: {e}", exc_info=True)
            await db.rollback()
