#!/usr/bin/env python3
"""Script to add a contact to the database with proper ID handling."""

from supabase import create_client, Client

# Supabase credentials
SUPABASE_URL = "https://fglvokukcgykzzirdqlq.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImZnbHZva3VrY2d5a3p6aXJkcWxxIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3NDM0MDc3NiwiZXhwIjoyMDg5OTE2Nzc2fQ.B5P2sHUQ0-tssTsVzNSSEpzqHh0SUv1uFMDVCGAu53k"

# Contact details
CONTACT_NAME = "Muskan"
CONTACT_PHONE = "8171671211"
CONTACT_EMAIL = "edumichub@gmail.com"
TENANT_NAME = "Muskan"

# Initialize Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

try:
    print("Step 1: Checking existing tenants...")
    
    # Get all tenants to see structure
    tenant_response = supabase.table("tenants").select("id, name").execute()
    print(f"Existing tenants: {len(tenant_response.data)} found")
    
    if tenant_response.data:
        for tenant in tenant_response.data:
            print(f"  - ID: {tenant['id']}, Name: {tenant['name']}")
    
    # Check if tenant exists
    print(f"\nStep 2: Looking for tenant '{TENANT_NAME}'...")
    tenant_search = supabase.table("tenants").select("id").eq("name", TENANT_NAME).execute()
    
    tenant_id = None
    if tenant_search.data:
        tenant_id = tenant_search.data[0]["id"]
        print(f"✓ Found tenant: {TENANT_NAME} (ID: {tenant_id})")
    else:
        print(f"✗ Tenant '{TENANT_NAME}' not found")
        
        # Find max ID and generate next one
        if tenant_response.data:
            max_id = max(t["id"] for t in tenant_response.data)
            new_id = max_id + 1
        else:
            new_id = 1
        
        print(f"  Creating new tenant with ID: {new_id}")
        
        tenant_insert = supabase.table("tenants").insert({
            "id": new_id,
            "name": TENANT_NAME,
            "default_language": "en",
            "is_active": True
        }).execute()
        
        if tenant_insert.data:
            tenant_id = tenant_insert.data[0]["id"]
            print(f"✓ Created tenant: {TENANT_NAME} (ID: {tenant_id})")
        else:
            print(f"✗ Failed to create tenant: {tenant_insert}")
            exit(1)
    
    # Now add contact
    print(f"\nStep 3: Adding contact to tenant {tenant_id}...")
    
    # Check existing contacts to get max ID
    contact_response = supabase.table("contacts").select("id").execute()
    if contact_response.data:
        max_contact_id = max(c["id"] for c in contact_response.data)
        new_contact_id = max_contact_id + 1
    else:
        new_contact_id = 1
    
    print(f"  New contact ID will be: {new_contact_id}")
    
    contact_data = {
        "id": new_contact_id,
        "tenant_id": tenant_id,
        "name": CONTACT_NAME,
        "email": CONTACT_EMAIL,
        "phone": CONTACT_PHONE,
        "language": "en"
    }
    
    insert_response = supabase.table("contacts").insert(contact_data).execute()
    
    if insert_response.data:
        contact = insert_response.data[0]
        print(f"\n✓ Contact added successfully!")
        print(f"  - ID: {contact['id']}")
        print(f"  - Name: {contact['name']}")
        print(f"  - Email: {contact['email']}")
        print(f"  - Phone: {contact['phone']}")
        print(f"  - Tenant ID: {contact['tenant_id']}")
    else:
        print(f"✗ Failed to add contact: {insert_response}")
        exit(1)

except Exception as e:
    print(f"✗ Error: {str(e)}")
    import traceback
    traceback.print_exc()
    exit(1)

print("\n✓ Done!")
