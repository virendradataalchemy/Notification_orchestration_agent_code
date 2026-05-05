import asyncio
import httpx

async def test():
    # 1. Get token
    auth_url = "http://localhost:8000/api/v1/auth/login"
    auth_data = {
        "username": "demo_corp",
        "password": "password123"
    }
    
    async with httpx.AsyncClient() as client:
        res = await client.post(auth_url, data=auth_data)
        token = res.json().get("access_token")
        
        headers = {"Authorization": f"Bearer {token}"}
        
        invite_url = "http://localhost:8000/api/v1/tenant/team/invite"
        invite_payload = {
            "emails": [
                "gaur.prateek.1609@gmail.com",
                "prachikushwaha.dataalchemy@gmail.com"
            ],
            "role": "member",
            "channels": ["email", "sms"],
            "delivery_mode": "parallel_all"
        }
        print(f"Testing Invite API: {invite_url}")
        res = await client.post(invite_url, json=invite_payload, headers=headers)
        print(f"Invite Response ({res.status_code}): {res.text}")

asyncio.run(test())
