import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from src.api.schemas import BatchNotificationResponse
from src.sdk.notifications import send_batch_notification_pipeline

# Payload file location
PAYLOAD_FILE = os.path.join(os.path.dirname(__file__), "batch_notification_payload.json")


def create_sample_payload():
    """Creates a sample JSON payload if it doesn't exist."""
    payload = {
        "tenant_id": "demo_corp",
        "request": {
            "subject": "Test Batch Alert",
            "body": "This is a batch notification testing payload from file.",
            "channel": "email",
            "data": {"common_key": "common_value"},
            "recipients": [
                {
                    "user_id": "user_101",
                    "email": "gaur.prateek.1609@gmail.com",
                    "phone": "+918290942415",
                    "data": {"name": "User 101"}
                },
                {
                    "user_id": "user_102",
                    "email": "gaur.prateek.1609@gmail.com",
                    "phone": "+918290942415",
                    "data": {"name": "User 102"}
                }
            ]
        }
    }
    with open(PAYLOAD_FILE, "w") as f:
        json.dump(payload, f, indent=4)
    print(f"Created sample batch payload at {PAYLOAD_FILE}")


def test_send_batch_notification_pipeline():
    """Pytest entry point for testing the batch pipeline."""
    if not os.path.exists(PAYLOAD_FILE):
        create_sample_payload()

    with open(PAYLOAD_FILE, "r") as f:
        payload = json.load(f)

    mock_response = BatchNotificationResponse(
        batch_id="batch_id_123",
        status="queued",
        total_recipients=len(payload["request"]["recipients"]),
    )

    with patch(
        "src.services.notification_service.NotificationService.send_batch_notifications",
        new_callable=AsyncMock,
    ) as mock_send:
        mock_send.return_value = mock_response

        response = send_batch_notification_pipeline(
            tenant_id=payload["tenant_id"],
            request=payload["request"],
            session=MagicMock(),
        )

        assert response.batch_id == "batch_id_123"
        assert response.total_recipients == 2
        mock_send.assert_awaited_once()


if __name__ == "__main__":
    import subprocess
    from pathlib import Path

    runner = Path(__file__).resolve().parent / "live_send_runner.py"
    print("Live send: spawning live_send_runner.py batch (real messages if stack is configured)...")
    raise SystemExit(
        subprocess.call(
            [sys.executable, str(runner), "batch", "--payload", str(Path(PAYLOAD_FILE).resolve())]
        )
    )
