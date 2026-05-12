import asyncio
import sys
sys.path.insert(0, '.')

from src.core.database import AsyncSessionLocal
from src.models import Template
from sqlalchemy import select

async def check_templates():
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Template))
        templates = result.scalars().all()
        
        print(f'Found {len(templates)} templates:\n')
        for t in templates:
            print(f'Template ID: {t.id}')
            print(f'  Name: {t.name}')
            print(f'  Channel: {t.channel}')
            print(f'  Tenant ID: {t.tenant_id}')
            print(f'  Provider Template Meta: {t.provider_template_meta}')
            print(f'  Body (first 200 chars): {t.body[:200] if t.body else "None"}')
            print('-' * 80)

if __name__ == "__main__":
    asyncio.run(check_templates())
