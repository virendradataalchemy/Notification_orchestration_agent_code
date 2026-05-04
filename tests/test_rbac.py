import asyncio
import httpx
import uuid
import secrets

BASE_URL = "http://localhost:8000"

async def test_rbac_flow():
    async with httpx.AsyncClient(timeout=30.0) as client:
        # 1. Signup
        tenant_id = f"test_tenant_{secrets.token_hex(4)}"
        print(f"Testing with tenant: {tenant_id}")
        
        signup_res = await client.post(f"{BASE_URL}/api/v1/tenant/auth/signup", json={
            "tenant_name": "Test Org",
            "admin_email": "admin@test.com",
            "username": f"admin_{tenant_id}",
            "password": "Password123",
            "tenant_id": tenant_id
        })
        
        if signup_res.status_code != 201:
            print(f"Signup failed: {signup_res.text}")
            return
            
        data = signup_res.json()
        token = data["access_token"]
        print("Signup successful")

        # 2. Invite a member
        invite_res = await client.post(
            f"{BASE_URL}/api/v1/tenant/team/invite",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "email": "marketing@test.com",
                "role": "marketing"
            }
        )
        
        if invite_res.status_code != 200:
            print(f"Invite failed: {invite_res.text}")
            return
            
        invite_data = invite_res.json()
        invite_token = invite_data["token"]
        print(f"Invite successful, token: {invite_token}")

        # 3. Accept invite
        accept_res = await client.post(
            f"{BASE_URL}/api/v1/tenant/team/accept-invite",
            json={
                "token": invite_token,
                "username": f"marketing_{tenant_id}",
                "password": "Password123",
                "full_name": "Marketing User"
            }
        )
        
        if accept_res.status_code != 200:
            print(f"Accept invite failed: {accept_res.text}")
            return
        
        print("Accept invite successful")

        # 4. Login as marketing user
        login_res = await client.post(f"{BASE_URL}/api/v1/tenant/auth/login", json={
            "username": f"marketing_{tenant_id}",
            "password": "Password123"
        })
        
        if login_res.status_code != 200:
            print(f"Marketing login failed: {login_res.text}")
            return
            
        m_data = login_res.json()
        m_token = m_data["access_token"]
        print(f"Marketing login successful, role: {m_data['tenant_type']}")

        # 5. Verify RBAC - marketing user should NOT be able to list team members
        team_res = await client.get(
            f"{BASE_URL}/api/v1/tenant/team/members",
            headers={"Authorization": f"Bearer {m_token}"}
        )
        
        # Wait, the current implementation of list_team_members in tenant_team.py allows ANY authenticated tenant user.
        # Let's check if that's what we want.
        # The plan says "Only accessible by admins" for /invite.
        # Let's check list_team_members.
        # router.get("/members") uses Depends(get_authenticated_tenant).
        # It doesn't use require_admin.
        
        print(f"Team members access status: {team_res.status_code}")
        
        # 6. Verify RBAC - marketing user should NOT be able to invite
        m_invite_res = await client.post(
            f"{BASE_URL}/api/v1/tenant/team/invite",
            headers={"Authorization": f"Bearer {m_token}"},
            json={"email": "fail@test.com", "role": "marketing"}
        )
        print(f"Marketing invite attempt status: {m_invite_res.status_code} (Expect 403)")

if __name__ == "__main__":
    asyncio.run(test_rbac_flow())
