import os
import asyncio
import httpx
from dotenv import load_dotenv

load_dotenv()

API_BASE_URL = os.getenv("DEMO_API_URL", "http://localhost:8000")
API_KEY = os.getenv("API_KEY", "sk_live_demo_corp_1_zR4zJo7aKCqujF11svKUM3Fsn3vwrESbsQ71CsDHA")
TENANT_ID = os.getenv("TENANT_ID", "demo_corp")
TEST_PHONE = os.getenv("TEST_RECEIVER_PHONE", "+13509308394")

async def test_voice():
    print(f"Testing VOICE channel to {TEST_PHONE}")
    import uuid
    uid = str(uuid.uuid4())
    payload = {
        "recipient": {"user_id": "user_1", "phone": TEST_PHONE},
        "notification": {
            "type": "alert",
            "priority": "critical",
            "channels": ["voice"],
            "idempotency_key": uid,
            "data": {
                "message": f"This is a critical voice alert from your AI Agent. Run {uid[:8]}.",
                "voice": "Polly.Amy",
                "language": "en-GB"
            }
        }
    }

    headers = {
        "X-API-Key": API_KEY,
        "X-Tenant-Id": TENANT_ID,
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{API_BASE_URL}/api/v1/notifications/send",
                json=payload,
                headers=headers,
                timeout=30.0
            )

            print(f"Status Code: {response.status_code}")
            print(f"Response: {response.text}")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_voice())
