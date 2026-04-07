import asyncio
import httpx
from colorama import init, Fore

API_BASE_URL = "http://localhost:8000"
API_KEY = "sk_live_demo_corp_m1UxVyIM67QKaSxTTGYqg244DObbChfZ78Te09o7Wy0"

async def test_voice():
    print("Testing Voice Notification...")
    
    headers = {
        "x-api-key": API_KEY,
        "x-tenant-id": "demo_corp",
        "Content-Type": "application/json"
    }
    
    # Notice we ask for the 'voice' channel
    payload = {
        "user_id": "usr_voice_tester",
        "title": "Voice Notification Test",
        "message": "Hello, this is a test voice message from your notification system.",
        "channels": ["voice"], 
        "priority": "high",
        "context": {
            # Make sure this is a valid phone number format (+1234567890)
            "contact_phone": "+1234567890"  
        }
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(f"{API_BASE_URL}/api/v1/notifications/send", json=payload, headers=headers)
            print(Fore.GREEN + f"Status: {response.status_code}")
            print(Fore.CYAN + "Response:")
            import json
            print(json.dumps(response.json(), indent=2))
        except Exception as e:
            print(Fore.RED + f"Error: {e}")

if __name__ == "__main__":
    init(autoreset=True)
    asyncio.run(test_voice())
