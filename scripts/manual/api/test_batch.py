import json
import httpx
import asyncio

async def test_batch_multichannel():
    payload = {
        "subject": "Test subject",
        "body": None,
        "template_id": None,
        "channels": ["email"],
        "channel_template_map": {
            "email": "welcome_email",
        },
        "recipients": [
            {
                "user_id": "u1",
                "email": "test@example.com",
                "phone": "+1234567890"
            }
        ],
        "data": {"campaign": "marketing_broadcast", "source": "marketing_hub"}
    }
    
    async with httpx.AsyncClient() as client:
        # Now send using API Key
        headers = {
            "X-API-Key": "sk_live_demo_corp_m1UxVyIM67QKaSxTTGYqg244DObbChfZ78Te09o7Wy0",
            "X-Tenant-Id": "demo_corp",
            "Content-Type": "application/json"
        }
        resp = await client.post("http://localhost:8000/api/v1/notifications/batch-multichannel",
                                 json=payload, headers=headers, timeout=30.0)
        print("Status Code:", resp.status_code)
        print("Response:", resp.text)

asyncio.run(test_batch_multichannel())