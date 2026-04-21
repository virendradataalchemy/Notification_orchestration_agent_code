"""Quick script to add a WhatsApp contact - edit the values below and run."""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.supabase import supabase_client


# ============================================================
# EDIT THESE VALUES
# ============================================================
TENANT_ID = 1  # Change to your tenant ID
NAME = "New Contact"
WHATSAPP_NUMBER = "+919876543210"  # Must include country code with +
EMAIL = None  # Optional: "contact@example.com" or None
PHONE = None  # Optional: "+919876543210" or None
JOB_TITLE = None  # Optional
COMPANY = None  # Optional
LANGUAGE = "en"
# ============================================================


async def quick_add():
    """Quickly add a WhatsApp contact."""
    
    print("=" * 60)
    print("Quick Add WhatsApp Contact")
    print("=" * 60)
    
    # Validate WhatsApp number
    if not WHATSAPP_NUMBER.startswith('+'):
        print("\n✗ Error: WhatsApp number must start with + and country code")
        print(f"   Current value: {WHATSAPP_NUMBER}")
        print("   Example: +919893155055")
        return
    
    # Get the next ID
    latest_contacts = await supabase_client.select(
        "contacts",
        "id",
        limit=1,
        filters={"order": "id.desc"}
    )
    next_id = int(latest_contacts[0]["id"]) + 1 if latest_contacts else 1
    
    # Create the contact
    contact_data = {
        "id": next_id,
        "tenant_id": TENANT_ID,
        "name": NAME,
        "email": EMAIL,
        "phone": PHONE,
        "whatsapp_number": WHATSAPP_NUMBER,
        "job_title": JOB_TITLE,
        "company": COMPANY,
        "language": LANGUAGE,
        "timezone": None,
        "metadata": None
    }
    
    print("\nAdding contact:")
    print(f"  Tenant ID: {TENANT_ID}")
    print(f"  Name: {NAME}")
    print(f"  WhatsApp: {WHATSAPP_NUMBER}")
    if EMAIL:
        print(f"  Email: {EMAIL}")
    if PHONE:
        print(f"  Phone: {PHONE}")
    
    try:
        result = await supabase_client.insert("contacts", contact_data)
        
        print("\n✓ Contact created successfully!")
        print(f"  Contact ID: {result[0]['id']}")
        print(f"  Name: {result[0]['name']}")
        print(f"  WhatsApp: {result[0]['whatsapp_number']}")
        
    except Exception as e:
        print(f"\n✗ Error creating contact: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(quick_add())
