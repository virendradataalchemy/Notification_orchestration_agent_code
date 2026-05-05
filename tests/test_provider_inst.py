import asyncio
from src.core.database import AsyncSessionLocal
from src.providers.mailgun_provider import MailgunProvider
from sqlalchemy import select
from src.models.tenant import TenantProviderConfig
from src.config import settings

async def test_provider():
    print(f"Settings API Key: {settings.mailgun_api_key}")
    async with AsyncSessionLocal() as db:
        query = select(TenantProviderConfig).where(
            TenantProviderConfig.tenant_id == 'demo_corp',
            TenantProviderConfig.provider == 'email',
            TenantProviderConfig.is_active == True,
        )
        result = await db.execute(query)
        row = result.scalar_one_or_none()
        config = row.config if row else {}
        print(f"DB config: {config}")

        provider = MailgunProvider(config=config)
        print(f"Provider API Key: {provider.api_key}")
        print(f"Provider Domain: {provider.domain}")

asyncio.run(test_provider())
