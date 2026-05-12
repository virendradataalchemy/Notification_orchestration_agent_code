"""
Send real notifications via the SDK using JSON payloads in this folder.

Run from anywhere:
  python src/sdk/tests/live_send_runner.py single
  python src/sdk/tests/live_send_runner.py batch
  python src/sdk/tests/live_send_runner.py multichannel

Loads repo-root .env / .env.local before importing application code so DATABASE_URL
and provider keys match your environment.

Use --dry-run to print the payload without sending.

Default tenant is ``demo_corp`` (see ``scripts/seed_tenant.py``). Pro tier has
unlimited quota in development (see ``usage_tracker.check_quota``).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _tests_dir() -> Path:
    return Path(__file__).resolve().parent


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _bootstrap() -> None:
    root = _repo_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(root / ".env")
    load_dotenv(root / ".env.local", override=True)


def _default_notification_payload() -> dict:
    return {
        "tenant_id": "demo_corp",
        "recipient": {
            "user_id": "user_123",
            "email": "gaur.prateek.1609@gmail.com",
            "phone": "+918290942415",
            "device_tokens": ["token_1"],
        },
        "notification": {
            "type": "alert",
            "priority": "high",
            "channels": ["email"],
            "subject": "Test Alert (live runner)",
            "body": "This is a real notification from live_send_runner.py (single).",
        },
        "options": {"track_opens": True, "track_clicks": True},
    }


def _default_batch_payload() -> dict:
    return {
        "tenant_id": "demo_corp",
        "request": {
            "subject": "Test Batch Alert (live runner)",
            "body": "Real batch send from live_send_runner.py.",
            "channel": "email",
            "data": {"common_key": "common_value"},
            "recipients": [
                {
                    "user_id": "user_101",
                    "email": "gaur.prateek.1609@gmail.com",
                    "phone": "+918290942415",
                    "data": {"name": "User 101"},
                },
                {
                    "user_id": "user_102",
                    "email": "gaur.prateek.1609@gmail.com",
                    "phone": "+918290942415",
                    "data": {"name": "User 102"},
                },
            ],
        },
    }


def _default_multichannel_payload() -> dict:
    return {
        "tenant_id": "demo_corp",
        "request": {
            "subject": "Test multichannel batch (live runner)",
            "body": "Real multichannel send from live_send_runner.py.",
            "channels": ["email", "sms"],
            "data": {"campaign": "live_runner"},
            "recipients": [
                {
                    "user_id": "user_201",
                    "email": "gaur.prateek.1609@gmail.com",
                    "phone": "+918290942415",
                    "data": {"name": "User 201"},
                },
                {
                    "user_id": "user_202",
                    "email": "gaur.prateek.1609@gmail.com",
                    "phone": "+918290942415",
                    "data": {"name": "User 202"},
                },
            ],
        },
    }


def _ensure_payload(path: Path, default: dict) -> dict:
    if not path.exists():
        path.write_text(json.dumps(default, indent=4), encoding="utf-8")
        print(f"Wrote default payload to {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _run_single(payload_path: Path, dry_run: bool) -> int:
    payload = _ensure_payload(payload_path, _default_notification_payload())
    if dry_run:
        print(json.dumps(payload, indent=2))
        return 0
    _bootstrap()
    from src.sdk.notifications import send_notification_pipeline

    response = send_notification_pipeline(
        tenant_id=payload["tenant_id"],
        recipient=payload["recipient"],
        notification=payload["notification"],
        options=payload.get("options"),
    )
    print(response)
    return 0


def _run_batch(payload_path: Path, dry_run: bool) -> int:
    payload = _ensure_payload(payload_path, _default_batch_payload())
    if dry_run:
        print(json.dumps(payload, indent=2))
        return 0
    _bootstrap()
    from src.sdk.notifications import send_batch_notification_pipeline

    response = send_batch_notification_pipeline(
        tenant_id=payload["tenant_id"],
        request=payload["request"],
    )
    print(response)
    return 0


def _run_multichannel(payload_path: Path, dry_run: bool) -> int:
    payload = _ensure_payload(payload_path, _default_multichannel_payload())
    if dry_run:
        print(json.dumps(payload, indent=2))
        return 0
    _bootstrap()
    from src.sdk.notifications import send_batch_multichannel_notification_pipeline

    response = send_batch_multichannel_notification_pipeline(
        tenant_id=payload["tenant_id"],
        request=payload["request"],
    )
    print(response)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Live SDK sends using JSON payloads.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_single = sub.add_parser("single", help="send_notification_pipeline")
    p_single.add_argument(
        "--payload",
        type=Path,
        default=_tests_dir() / "notification_payload.json",
        help="Path to JSON (tenant_id, recipient, notification, options)",
    )
    p_single.add_argument("--dry-run", action="store_true")

    p_batch = sub.add_parser("batch", help="send_batch_notification_pipeline")
    p_batch.add_argument(
        "--payload",
        type=Path,
        default=_tests_dir() / "batch_notification_payload.json",
        help="Path to JSON (tenant_id, request)",
    )
    p_batch.add_argument("--dry-run", action="store_true")

    p_mc = sub.add_parser("multichannel", help="send_batch_multichannel_notification_pipeline")
    p_mc.add_argument(
        "--payload",
        type=Path,
        default=_tests_dir() / "batch_multichannel_notification_payload.json",
        help="Path to JSON (tenant_id, request)",
    )
    p_mc.add_argument("--dry-run", action="store_true")

    args = parser.parse_args(argv)
    if args.command == "single":
        return _run_single(args.payload, args.dry_run)
    if args.command == "batch":
        return _run_batch(args.payload, args.dry_run)
    if args.command == "multichannel":
        return _run_multichannel(args.payload, args.dry_run)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
