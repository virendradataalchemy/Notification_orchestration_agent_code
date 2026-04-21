#!/usr/bin/env python
"""
Worker entry point - currently disabled.

Notification delivery is handled directly via async/await in the API process.
No separate worker process is needed at this time.

To re-enable background processing, uncomment below and implement a
Supabase-based polling worker.
"""

# import asyncio
# import logging
# import sys
# from src.workers.tenant_aware_worker import worker
#
# logging.basicConfig(
#     level=logging.INFO,
#     format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
#     handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler("worker.log")]
# )
# logger = logging.getLogger(__name__)
#
# if __name__ == "__main__":
#     logger.info("TENANT-AWARE NOTIFICATION WORKER STARTING")
#     try:
#         asyncio.run(worker.start(poll_interval=5))
#     except KeyboardInterrupt:
#         worker.stop()

if __name__ == "__main__":
    print("Worker is currently disabled. Notifications are sent directly via the API.")
    print("See run_worker.py for re-enabling instructions.")
