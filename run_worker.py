#!/usr/bin/env python
"""Run the tenant-aware notification worker to process queued notifications."""

import asyncio
import logging
import sys

from src.workers.tenant_aware_worker import worker

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("worker.log")
    ]
)

logger = logging.getLogger(__name__)


if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("TENANT-AWARE NOTIFICATION WORKER STARTING")
    logger.info("=" * 60)
    logger.info("This worker processes queued notifications with tenant-specific configs")
    logger.info("Poll interval: 5 seconds")
    logger.info("Press Ctrl+C to stop")
    logger.info("=" * 60)

    try:
        asyncio.run(worker.start(poll_interval=5))
    except KeyboardInterrupt:
        logger.info("\nWorker stopped by user")
        worker.stop()
    except Exception as e:
        logger.error(f"Worker failed: {e}", exc_info=True)
        sys.exit(1)
