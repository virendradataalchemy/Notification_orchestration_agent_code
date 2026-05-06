import urllib.request
import json
import time

def login():
    req = urllib.request.Request(
        'http://localhost:8000/api/v1/tenant/auth/login',
        data=json.dumps({
            'username': 'admin',
            'password': 'Password123!'
        }).encode('utf-8'),
        headers={'Content-Type': 'application/json'}
    )
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode())
    except Exception as e:
        return {'error': str(e)}

res = login()
if 'access_token' in res:
    token = res['access_token']
    
    # 1. Check current team members
    req2 = urllib.request.Request(
        'http://localhost:8000/api/v1/tenant/team/members',
        headers={
            'Authorization': f'Bearer {token}'
        }
    )
    with urllib.request.urlopen(req2) as response2:
        members = json.loads(response2.read().decode())
        print('Members before update:')
        for m in members:
            print(f"  {m['username']}: {m['full_name']}")
        
    # 2. Update profile
    new_name = 'Demo Admin Final ' + str(int(time.time()))
    req3 = urllib.request.Request(
        'http://localhost:8000/api/v1/tenant/settings/profile',
        data=json.dumps({
            'admin_name': new_name
        }).encode('utf-8'),
        headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {token}'
        },
        method='PATCH'
    )
    with urllib.request.urlopen(req3) as response3:
        profile = json.loads(response3.read().decode())
        print('\nProfile updated to:', profile['admin_name'])
        
    # 3. Check team members again
    req4 = urllib.request.Request(
        'http://localhost:8000/api/v1/tenant/team/members',
        headers={
            'Authorization': f'Bearer {token}'
        }
    )
    with urllib.request.urlopen(req4) as response4:
        members_after = json.loads(response4.read().decode())
        print('\nMembers after update:')
        for m in members_after:
            print(f"  {m['username']}: {m['full_name']}")

else:
    print('Login failed:', res)