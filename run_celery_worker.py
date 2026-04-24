#!/usr/bin/env python
"""Thin launcher for Celery worker used by notification tasks."""

import os
import subprocess
import sys


def main() -> int:
    """
    Start Celery worker for notification queues.

    Defaults:
    - Windows-safe pool: solo
    - Queues: critical,high,medium,low
    - Log level: info

    Environment overrides:
    - CELERY_POOL
    - CELERY_QUEUES
    - CELERY_LOGLEVEL
    """
    pool = os.getenv("CELERY_POOL", "solo")
    queues = os.getenv("CELERY_QUEUES", "critical,high,medium,low")
    loglevel = os.getenv("CELERY_LOGLEVEL", "info")

    cmd = [
        sys.executable,
        "-m",
        "celery",
        "-A",
        "src.celery_app:celery_app",
        "worker",
        "--pool",
        pool,
        "-Q",
        queues,
        "-l",
        loglevel,
    ]

    print("Starting Celery worker:")
    print(" ".join(cmd))
    return subprocess.call(cmd)


if __name__ == "__main__":
    raise SystemExit(main())
