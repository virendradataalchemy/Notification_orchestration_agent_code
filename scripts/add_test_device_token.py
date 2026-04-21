#!/usr/bin/env python3
"""
Add a test device token to a contact for push notification testing.
"""

import asyncio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.supabase import supabase_client
from datetime import datetime


async def add_device_token(contact_id: int, device_token: str, platform: str = "android"):
    """Add a device token for a contact."""
    try:
        # Check if contact exists
        contacts = await supabase_client.select(
            "contacts",
            "id,name,tenant_id",
            filters={"id": f"eq.{contact_id}"},
            limit=1
        )
        
        if not contacts:
            print(f"❌ Contact with ID {contact_id} not found!")
            return False
        
        contact = contacts[0]
        print(f"✅ Found contact: {contact['name']} (Tenant ID: {contact['tenant_id']})")
        
        # Check if token already exists
        existing = await supabase_client.select(
            "device_tokens",
            "id,is_active",
            filters={
                "contact_id": f"eq.{contact_id}",
                "device_token": f"eq.{device_token}"
            },
            limit=1
        )
        
        if existing:
            print(f"⚠️  Device token already exists (ID: {existing[0]['id']})")
            
            # Update it
            await supabase_client.update(
                "device_tokens",
                {
                    "is_active": True,
                    "platform": platform,
                    "last_used_at": datetime.utcnow().isoformat(),
                    "updated_at": datetime.utcnow().isoformat()
                },
                filters={"id": f"eq.{existing[0]['id']}"}
            )
            print(f"✅ Updated device token to active")
            return True
        
        # Get next ID
        latest = await supabase_client.select(
            "device_tokens",
            "id",
            limit=1,
            filters={"order": "id.desc"}
        )
        next_id = int(latest[0]["id"]) + 1 if latest else 1
        
        # Insert new token
        result = await supabase_client.insert(
            "device_tokens",
            {
                "id": next_id,
                "contact_id": contact_id,
                "device_token": device_token,
                "platform": platform,
                "is_active": True,
                "last_used_at": datetime.utcnow().isoformat(),
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat()
            }
        )
        
        print(f"✅ Device token added successfully!")
        print(f"   Token ID: {result[0]['id']}")
        print(f"   Contact: {contact['name']}")
        print(f"   Platform: {platform}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


async def list_device_tokens(contact_id: int = None):
    """List all device tokens or for a specific contact."""
    try:
        if contact_id:
            filters = {"contact_id": f"eq.{contact_id}"}
        else:
            filters = {}
        
        tokens = await supabase_client.select(
            "device_tokens",
            "id,contact_id,device_token,platform,is_active,last_used_at,created_at",
            filters=filters
        )
        
        if not tokens:
            print("No device tokens found")
            return
        
        print(f"\n📱 Device Tokens ({len(tokens)} total):\n")
        for token in tokens:
            status = "✅ Active" if token.get("is_active") else "❌ Inactive"
            print(f"  ID: {token['id']}")
            print(f"  Contact ID: {token['contact_id']}")
            print(f"  Platform: {token.get('platform', 'unknown')}")
            print(f"  Status: {status}")
            print(f"  Token: {token['device_token'][:50]}...")
            print(f"  Last Used: {token.get('last_used_at', 'Never')}")
            print()
        
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  Add token:  python scripts/add_test_device_token.py add <contact_id> <device_token> [platform]")
        print("  List all:   python scripts/add_test_device_token.py list")
        print("  List by ID: python scripts/add_test_device_token.py list <contact_id>")
        print("\nExample:")
        print("  python scripts/add_test_device_token.py add 1 'test_device_token_123' android")
        sys.exit(1)
    
    command = sys.argv[1].lower()
    
    if command == "add":
        if len(sys.argv) < 4:
            print("❌ Error: Missing arguments")
            print("Usage: python scripts/add_test_device_token.py add <contact_id> <device_token> [platform]")
            sys.exit(1)
        
        contact_id = int(sys.argv[2])
        device_token = sys.argv[3]
        platform = sys.argv[4] if len(sys.argv) > 4 else "android"
        
        asyncio.run(add_device_token(contact_id, device_token, platform))
        
    elif command == "list":
        contact_id = int(sys.argv[2]) if len(sys.argv) > 2 else None
        asyncio.run(list_device_tokens(contact_id))
        
    else:
        print(f"❌ Unknown command: {command}")
        print("Valid commands: add, list")
