#!/usr/bin/env python3
"""Script to add a contact via API."""

import requests
import json

API_URL = "http://localhost:8000"

# First, get or create tenant
print("Step 1: Checking for tenant 'Muskan'...")

# Since we don't have a direct tenant endpoint, let's query contacts to find existing tenant
# Let me try calling the API directly
try:
    # Try to get contacts - this will help us understand the API structure
    response = requests.get(f"{API_URL}/contacts", headers={"X-Tenant-ID": "1"})
    print(f"Response status: {response.status_code}")
    
    # Let's create a contact directly with tenant_id from existing data
    # First, check what tenants exist by querying the dashboard or admin endpoints
    
    admin_response = requests.get(f"{API_URL}/admin/tenants")
    print(f"Admin tenants response: {admin_response.status_code}")
    if admin_response.status_code == 200:
        print("Admin tenants:", json.dumps(admin_response.json(), indent=2))
    
except Exception as e:
    print(f"Error: {e}")
