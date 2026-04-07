"""Test Mailgun configuration and send a test email."""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import settings
from src.providers.mailgun_provider import MailgunProvider
from src.providers.base import Message


async def test_mailgun():
    """Test Mailgun provider configuration and send a test email."""
    
    print("=" * 60)
    print("Mailgun Configuration Test")
    print("=" * 60)
    
    print(f"\nAPI Key: {settings.mailgun_api_key[:20]}..." if settings.mailgun_api_key else "Not set")
    print(f"Domain: {settings.mailgun_domain}")
    print(f"From Email: {settings.mailgun_from_email}")
    print(f"Base URL: {settings.mailgun_base_url}")
    
    provider = MailgunProvider()
    
    print(f"\nProvider Configuration:")
    print(f"  API Key: {provider.api_key[:20]}..." if provider.api_key else "Not set")
    print(f"  Domain: {provider.domain}")
    print(f"  From Email: {provider.from_email}")
    print(f"  Base URL: {provider.base_url}")
    
    # Construct the full URL
    full_url = f"{provider.base_url}/{provider.domain}/messages"
    print(f"\nFull API URL: {full_url}")
    
    # Test sending an email
    print("\n" + "=" * 60)
    print("Sending Test Email")
    print("=" * 60)
    
    test_message = Message(
        recipient="edumichub@gmail.com",
        subject="Test Email from Mailgun",
        body="This is a test email to verify Mailgun configuration.",
        data={"test": True},
        metadata={"source": "test_script"}
    )
    
    print(f"\nSending to: {test_message.recipient}")
    print(f"Subject: {test_message.subject}")
    
    try:
        response = await provider.send(test_message)
        
        print(f"\nResponse Status: {response.status}")
        print(f"Message ID: {response.message_id}")
        
        if response.status.value == "success":
            print("\n✓ Email sent successfully!")
        else:
            print(f"\n✗ Email failed to send")
            print(f"Error Code: {response.error_code}")
            print(f"Error Message: {response.error_message}")
            
    except Exception as e:
        print(f"\n✗ Exception occurred: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_mailgun())
