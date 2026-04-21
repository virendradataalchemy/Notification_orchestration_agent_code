"""Update email provider from sendgrid to mailgun in the database."""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.supabase import supabase_client


async def update_email_provider():
    """Update the email provider from sendgrid to mailgun."""
    
    print("Checking current email provider...")
    
    # Get current email providers
    providers = await supabase_client.select(
        "providers",
        "*",
        filters={"channel_id": "eq.5"}  # channel_id 5 is email
    )
    
    print(f"Found {len(providers)} email provider(s):")
    for provider in providers:
        print(f"  - ID: {provider['id']}, Name: {provider['name']}, Active: {provider['is_active']}")
    
    # Update sendgrid to mailgun
    for provider in providers:
        if provider['name'] == 'sendgrid':
            print(f"\nUpdating provider ID {provider['id']} from 'sendgrid' to 'mailgun'...")
            
            await supabase_client.update(
                "providers",
                {"name": "mailgun"},
                filters={"id": f"eq.{provider['id']}"}
            )
            
            print(f"✓ Successfully updated provider ID {provider['id']} to 'mailgun'")
    
    # Verify the update
    print("\nVerifying update...")
    updated_providers = await supabase_client.select(
        "providers",
        "*",
        filters={"channel_id": "eq.5"}
    )
    
    print(f"Updated email provider(s):")
    for provider in updated_providers:
        print(f"  - ID: {provider['id']}, Name: {provider['name']}, Active: {provider['is_active']}")
    
    print("\n✓ Email provider successfully updated to Mailgun!")


if __name__ == "__main__":
    asyncio.run(update_email_provider())
