"""
Debug script to check branding configuration
"""
import asyncio
import sys
sys.path.insert(0, '.')

from src.core.database import AsyncSessionLocal
from src.models import TenantBranding
from sqlalchemy import select

async def debug_branding():
    print("=" * 70)
    print("Branding Debug".center(70))
    print("=" * 70)
    
    tenant_id = input("\nEnter Tenant ID (default: demo_corp): ").strip() or "demo_corp"
    
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(TenantBranding).where(TenantBranding.tenant_id == tenant_id)
        )
        branding = result.scalar_one_or_none()
        
        if not branding:
            print(f"\n❌ No branding found for tenant '{tenant_id}'")
            print("\n💡 To fix:")
            print("   1. Open template editor in browser")
            print("   2. Fill in Company Branding section")
            print("   3. Click 'Save Branding Globally'")
            return
        
        print(f"\n✅ Branding found: {branding.id}")
        print("\n" + "=" * 70)
        print("Branding Configuration:")
        print("=" * 70)
        print(f"Enabled: {branding.enabled}")
        print(f"Logo URL: {branding.logo_url or '❌ NOT SET'}")
        print(f"Company Name: {branding.company_name or '❌ NOT SET'}")
        print(f"Theme Color: {branding.theme_color}")
        print(f"Contact Phone: {branding.contact_phone or '❌ NOT SET'}")
        print(f"Contact Email: {branding.contact_email or '❌ NOT SET'}")
        print(f"Website: {branding.website or '❌ NOT SET'}")
        print(f"Custom Footer HTML: {'✅ SET' if branding.footer_html else '❌ NOT SET'}")
        
        # Check logo URL
        print("\n" + "=" * 70)
        print("Logo Analysis:")
        print("=" * 70)
        
        if not branding.logo_url:
            print("❌ Logo URL is empty!")
            print("\n💡 To fix:")
            print("   1. Open template editor")
            print("   2. Expand Company Branding section")
            print("   3. Fill in 'Company logo' field with a URL")
            print("   4. Click 'Save Branding Globally'")
        elif branding.logo_url.startswith('data:'):
            print("✅ Logo is a base64 data URI")
            print(f"   Length: {len(branding.logo_url)} characters")
            print(f"   Preview: {branding.logo_url[:100]}...")
        elif branding.logo_url.startswith('http'):
            print("✅ Logo is a public URL")
            print(f"   URL: {branding.logo_url}")
            print("\n⚠️  Make sure this URL is publicly accessible!")
        else:
            print(f"⚠️  Unusual logo URL format: {branding.logo_url[:100]}")
        
        # Test rendering
        print("\n" + "=" * 70)
        print("Testing Footer Rendering:")
        print("=" * 70)
        
        from src.services.tenant_template_engine import TenantTemplateEngine
        engine = TenantTemplateEngine()
        
        test_data = {"user": {"name": "Test User"}}
        footer_html = engine.render_branding_footer_html(branding, test_data)
        
        if 'notification-branding-footer' in footer_html:
            print("✅ Footer HTML generated successfully")
        else:
            print("❌ Footer HTML generation failed")
        
        if branding.logo_url and branding.logo_url in footer_html:
            print("✅ Logo URL is included in footer HTML")
        elif branding.logo_url:
            print("❌ Logo URL is NOT in footer HTML")
            print("   This is a bug in the template engine!")
        
        # Save test output
        with open("debug_footer_output.html", "w", encoding="utf-8") as f:
            f.write(f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Branding Footer Test</title>
</head>
<body style="font-family: Arial, sans-serif; padding: 20px;">
    <h1>Test Email Content</h1>
    <p>This is the main email body.</p>
    
    {footer_html}
</body>
</html>
            """)
        
        print("\n✅ Test output saved to: debug_footer_output.html")
        print("   Open this file in a browser to see if the logo appears")
        
        print("\n" + "=" * 70)
        print("Summary:")
        print("=" * 70)
        if branding.logo_url:
            print("✅ Logo URL is configured")
            print("📧 If logo still doesn't show in emails:")
            print("   1. Check if URL is publicly accessible")
            print("   2. Check email client image settings")
            print("   3. Try using a base64 data URI instead")
        else:
            print("❌ Logo URL is NOT configured")
            print("   → Set it in the template editor and save globally")

if __name__ == "__main__":
    asyncio.run(debug_branding())
