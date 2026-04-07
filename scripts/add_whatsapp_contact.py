"""Add a new contact with WhatsApp number to the database."""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.supabase import supabase_client


async def add_whatsapp_contact():
    """Add a new contact with WhatsApp number."""
    
    print("=" * 60)
    print("Add WhatsApp Contact")
    print("=" * 60)
    
    # Get tenant selection
    tenants = await supabase_client.select("tenants", "id,name", filters={"is_active": "eq.true"})
    
    if not tenants:
        print("No active tenants found!")
        return
    
    print("\nAvailable Tenants:")
    for tenant in tenants:
        print(f"  {tenant['id']}: {tenant['name']}")
    
    tenant_id = input("\nEnter Tenant ID: ").strip()
    
    # Get contact details
    print("\n" + "=" * 60)
    print("Enter Contact Details")
    print("=" * 60)
    
    name = input("Name: ").strip()
    email = input("Email (optional, press Enter to skip): ").strip() or None
    phone = input("Phone (optional, press Enter to skip): ").strip() or None
    whatsapp_number = input("WhatsApp Number (with country code, e.g., +919893155055): ").strip()
    
    if not whatsapp_number:
        print("\n✗ WhatsApp number is required!")
        return
    
    # Validate WhatsApp number format
    if not whatsapp_number.startswith('+'):
        print("\n✗ WhatsApp number must start with + and country code (e.g., +919893155055)")
        return
    
    job_title = input("Job Title (optional): ").strip() or None
    company = input("Company (optional): ").strip() or None
    language = input("Language (default: en): ").strip() or "en"
    
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
        "tenant_id": int(tenant_id),
        "name": name,
        "email": email,
        "phone": phone,
        "whatsapp_number": whatsapp_number,
        "job_title": job_title,
        "company": company,
        "language": language,
        "timezone": None,
        "metadata": None
    }
    
    print("\n" + "=" * 60)
    print("Contact to be created:")
    print("=" * 60)
    for key, value in contact_data.items():
        if value is not None:
            print(f"  {key}: {value}")
    
    confirm = input("\nCreate this contact? (yes/no): ").strip().lower()
    
    if confirm != 'yes':
        print("\n✗ Contact creation cancelled.")
        return
    
    try:
        result = await supabase_client.insert("contacts", contact_data)
        
        print("\n" + "=" * 60)
        print("✓ Contact created successfully!")
        print("=" * 60)
        print(f"Contact ID: {result[0]['id']}")
        print(f"Name: {result[0]['name']}")
        print(f"WhatsApp: {result[0]['whatsapp_number']}")
        print(f"Tenant ID: {result[0]['tenant_id']}")
        
    except Exception as e:
        print(f"\n✗ Error creating contact: {str(e)}")
        import traceback
        traceback.print_exc()


async def list_contacts():
    """List all contacts with WhatsApp numbers."""
    
    print("\n" + "=" * 60)
    print("Existing Contacts with WhatsApp")
    print("=" * 60)
    
    contacts = await supabase_client.select(
        "contacts",
        "id,tenant_id,name,email,phone,whatsapp_number",
        filters={"whatsapp_number": "not.is.null"}
    )
    
    if not contacts:
        print("No contacts with WhatsApp numbers found.")
        return
    
    for contact in contacts:
        print(f"\nID: {contact['id']}")
        print(f"  Tenant ID: {contact['tenant_id']}")
        print(f"  Name: {contact['name']}")
        print(f"  WhatsApp: {contact['whatsapp_number']}")
        if contact.get('email'):
            print(f"  Email: {contact['email']}")
        if contact.get('phone'):
            print(f"  Phone: {contact['phone']}")


async def main():
    """Main function."""
    
    print("\n" + "=" * 60)
    print("WhatsApp Contact Management")
    print("=" * 60)
    print("\n1. Add new contact with WhatsApp")
    print("2. List existing contacts with WhatsApp")
    print("3. Exit")
    
    choice = input("\nEnter your choice (1-3): ").strip()
    
    if choice == "1":
        await add_whatsapp_contact()
    elif choice == "2":
        await list_contacts()
    elif choice == "3":
        print("\nGoodbye!")
        return
    else:
        print("\n✗ Invalid choice!")


if __name__ == "__main__":
    asyncio.run(main())
