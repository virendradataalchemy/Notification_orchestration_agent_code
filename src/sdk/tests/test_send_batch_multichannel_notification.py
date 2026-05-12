import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from src.api.schemas import BatchMultiChannelNotificationResponse
from src.sdk.notifications import send_batch_multichannel_notification_pipeline

PAYLOAD_FILE = os.path.join(os.path.dirname(__file__), "batch_multichannel_notification_payload.json")


def create_sample_payload() -> None:
    payload = {
        "tenant_id": "demo_corp",
        "request": {
            "subject": "Test multichannel batch",
            "body": "Payload loaded from JSON for integration-style testing.",
            "channels": ["email", "sms"],
            "data": {"campaign": "file_driven_test"},
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
    with open(PAYLOAD_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=4)


def test_send_batch_multichannel_notification_pipeline() -> None:
    if not os.path.exists(PAYLOAD_FILE):
        create_sample_payload()

    with open(PAYLOAD_FILE, "r", encoding="utf-8") as f:
        payload = json.load(f)

    mock_response = BatchMultiChannelNotificationResponse(
        batch_id="batch_mc_123",
        status="processing",
        total_recipients=len(payload["request"]["recipients"]),
        total_notifications=4,
        total_channel_records=4,
        channels=["email", "sms"],
    )

    with patch(
        "src.services.notification_service.NotificationService.send_batch_notifications_multichannel",
        new_callable=AsyncMock,
    ) as mock_send:
        mock_send.return_value = mock_response

        response = send_batch_multichannel_notification_pipeline(
            tenant_id=payload["tenant_id"],
            request=payload["request"],
            session=MagicMock(),
        )

    assert response.batch_id == "batch_mc_123"
    assert response.total_recipients == 2
    mock_send.assert_awaited_once()


if __name__ == "__main__":
    import subprocess
    from pathlib import Path

    runner = Path(__file__).resolve().parent / "live_send_runner.py"
    print("Live send: spawning live_send_runner.py multichannel (real messages if stack is configured)...")
    raise SystemExit(
        subprocess.call(
            [
                sys.executable,
                str(runner),
                "multichannel",
                "--payload",
                str(Path(PAYLOAD_FILE).resolve()),
            ]
        )
    )
