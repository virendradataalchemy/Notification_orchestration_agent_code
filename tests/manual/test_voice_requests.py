import requests
import json

API_BASE_URL = "http://localhost:8000"
API_KEY = "sk_live_demo_corp_m1UxVyIM67QKaSxTTGYqg244DObbChfZ78Te09o7Wy0"

def test_voice():
    print("Testing Voice Notification...")
    
    headers = {
        "x-api-key": API_KEY,
        "x-tenant-id": "demo_corp",
        "Content-Type": "application/json"
    }
    
    payload = {
        "user_id": "usr_voice_tester",
        "title": "Voice Test",
        "message": "Hello, voice service test.",
        "channels": ["voice"], 
        "priority": "high",
        "context": {
            "contact_phone": "+19999999999"  
        }
    }

    try:
        response = requests.post(f"{API_BASE_URL}/api/v1/notifications/send", json=payload, headers=headers)
        print(f"Status: {response.status_code}")
        print("Response:")
        print(json.dumps(response.json(), indent=2))
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_voice()
