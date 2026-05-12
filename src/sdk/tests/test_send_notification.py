import json
import os
import sys
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from src.api.schemas import NotificationResponse, NotificationStatus
from src.sdk.notifications import send_notification_pipeline

# Payload file location
PAYLOAD_FILE = os.path.join(os.path.dirname(__file__), "notification_payload.json")


def create_sample_payload():
    """Creates a sample JSON payload if it doesn't exist."""
    payload = {
        "tenant_id": "demo_corp",
        "recipient": {
            "user_id": "user_123",
            "email": "gaur.prateek.1609@gmail.com",
            "phone": "+918290942415",
            "device_tokens": ["token_1"]
        },
        "notification": {
            "type": "alert",
            "priority": "high",
            "channels": ["email"],
            "subject": "Test Alert",
            "body": "This is a test notification from the file payload."
        },
        "options": {
            "track_opens": True,
            "track_clicks": True
        }
    }
    with open(PAYLOAD_FILE, "w") as f:
        json.dump(payload, f, indent=4)
    print(f"Created sample payload at {PAYLOAD_FILE}")


def test_send_notification_pipeline():
    """Pytest entry point for testing the pipeline."""
    if not os.path.exists(PAYLOAD_FILE):
        create_sample_payload()

    with open(PAYLOAD_FILE, "r") as f:
        payload = json.load(f)

    mock_response = NotificationResponse(
        notification_id="test_id_123",
        status=NotificationStatus.DELIVERED,
        channels={},
        created_at=datetime(2026, 5, 11, 0, 0, 0, tzinfo=timezone.utc),
    )

    with patch(
        "src.services.notification_service.NotificationService.send_notification",
        new_callable=AsyncMock,
    ) as mock_send:
        mock_send.return_value = mock_response

        response = send_notification_pipeline(
            tenant_id=payload["tenant_id"],
            recipient=payload["recipient"],
            notification=payload["notification"],
            options=payload.get("options"),
            session=MagicMock(),
        )

        assert response.notification_id == "test_id_123"
        mock_send.assert_awaited_once()


if __name__ == "__main__":
    # Delegate to live_send_runner so .env is loaded before any `src` imports (settings/DB URL).
    import subprocess
    from pathlib import Path

    runner = Path(__file__).resolve().parent / "live_send_runner.py"
    print("Live send: spawning live_send_runner.py single (real message if stack is configured)...")
    raise SystemExit(
        subprocess.call(
            [sys.executable, str(runner), "single", "--payload", str(Path(PAYLOAD_FILE).resolve())]
        )
    )
