"""
Quick setup script for tenant branding
"""
import asyncio
import sys
sys.path.insert(0, '.')

from src.core.database import AsyncSessionLocal
from src.models import TenantBranding
from sqlalchemy import select

async def setup_branding():
    print("=" * 70)
    print("Tenant Branding Setup".center(70))
    print("=" * 70)
    
    tenant_id = input("\nEnter Tenant ID (default: demo_corp): ").strip() or "demo_corp"
    
    async with AsyncSessionLocal() as db:
        # Check if branding already exists
        result = await db.execute(
            select(TenantBranding).where(TenantBranding.tenant_id == tenant_id)
        )
        existing = result.scalar_one_or_none()
        
        if existing:
            print(f"\n⚠️  Branding already exists for tenant '{tenant_id}'")
            print(f"   Logo: {existing.logo_url or 'Not set'}")
            print(f"   Company: {existing.company_name or 'Not set'}")
            
            update = input("\nUpdate existing branding? (y/n): ").strip().lower()
            if update != 'y':
                print("Cancelled.")
                return
            
            branding = existing
        else:
            branding = TenantBranding(
                tenant_id=tenant_id
            )
            db.add(branding)
        
        print("\n" + "-" * 70)
        print("Enter branding details (press Enter to skip):")
        print("-" * 70)
        
        # Logo URL
        print("\n📷 Logo URL:")
        print("   Options:")
        print("   1. Public URL: https://your-domain.com/logo.png")
        print("   2. Base64: data:image/png;base64,iVBORw0KGgo...")
        print("   3. Placeholder: https://via.placeholder.com/120x40")
        logo_url = input("   Enter logo URL: ").strip()
        if logo_url:
            branding.logo_url = logo_url
        
        # Company Name
        company_name = input("\n🏢 Company Name: ").strip()
        if company_name:
            branding.company_name = company_name
        
        # Theme Color
        print("\n🎨 Theme Color (hex code):")
        print("   Examples: #1d4ed8 (blue), #10b981 (green), #f59e0b (orange)")
        theme_color = input("   Enter color (default: #1d4ed8): ").strip() or "#1d4ed8"
        branding.theme_color = theme_color
        
        # Contact Email
        contact_email = input("\n📧 Contact Email: ").strip()
        if contact_email:
            branding.contact_email = contact_email
        
        # Contact Phone
        contact_phone = input("\n📞 Contact Phone: ").strip()
        if contact_phone:
            branding.contact_phone = contact_phone
        
        # Website
        website = input("\n🌐 Website: ").strip()
        if website:
            branding.website = website
        
        # Enable
        print("\n✅ Enable branding?")
        enabled = input("   (y/n, default: y): ").strip().lower() or 'y'
        branding.enabled = (enabled == 'y')
        
        # Save
        await db.commit()
        await db.refresh(branding)
        
        print("\n" + "=" * 70)
        print("✅ Branding Saved Successfully!".center(70))
        print("=" * 70)
        
        print(f"\nBranding ID: {branding.id}")
        print(f"Tenant ID: {branding.tenant_id}")
        print(f"Logo URL: {branding.logo_url or 'Not set'}")
        print(f"Company: {branding.company_name or 'Not set'}")
        print(f"Theme Color: {branding.theme_color}")
        print(f"Contact Email: {branding.contact_email or 'Not set'}")
        print(f"Contact Phone: {branding.contact_phone or 'Not set'}")
        print(f"Website: {branding.website or 'Not set'}")
        print(f"Enabled: {branding.enabled}")
        
        print("\n" + "-" * 70)
        print("Next Steps:")
        print("-" * 70)
        print("1. Test branding: python test_branding.py")
        print("2. Send email - branding will be automatically applied!")
        print("3. Preview via API: POST /api/v1/branding/preview")
        print("4. Update via API: POST /api/v1/branding")

if __name__ == "__main__":
    asyncio.run(setup_branding())
