#!/bin/sh
set -e

cd /app
export PYTHONPATH=/app${PYTHONPATH:+:$PYTHONPATH}

if [ ! -f /app/src/celery_app.py ]; then
  echo "ERROR: /app/src/celery_app.py not found."
  echo "The Celery container expects the project root (with src/) at /app."
  echo "If using docker-compose, run 'docker compose' from the repo root and avoid"
  echo "bind-mounting an empty or wrong host directory over /app."
  echo "Contents of /app:"
  ls -la /app 2>/dev/null || true
  exit 1
fi

exec "$@"
