"""
Check queued notifications in the database
"""

import asyncio
from sqlalchemy import select
from src.core.database import AsyncSessionLocal
from src.models import Notification, NotificationChannel, ChannelStatus
from colorama import init, Fore, Style
import json

init(autoreset=True)

async def check_queued():
    """Check all queued notification channels."""
    print("\n" + "=" * 80)
    print(f"{Fore.CYAN}{Style.BRIGHT}{'QUEUED NOTIFICATIONS CHECK'.center(80)}{Style.RESET_ALL}")
    print("=" * 80 + "\n")

    async with AsyncSessionLocal() as db:
        # Get all queued channels with their notifications
        query = (
            select(NotificationChannel, Notification)
            .join(Notification, NotificationChannel.notification_id == Notification.id)
            .where(NotificationChannel.status == ChannelStatus.QUEUED)
            .limit(20)
        )

        result = await db.execute(query)
        records = result.all()

        if not records:
            print(f"{Fore.GREEN}No queued notifications found.{Style.RESET_ALL}")
            print("All notifications have been processed!")
            return

        print(f"Found {Fore.YELLOW}{len(records)}{Style.RESET_ALL} queued notification channels:\n")

        for i, (channel_record, notification) in enumerate(records, 1):
            print(f"{Fore.CYAN}#{i} Notification ID: {notification.id}{Style.RESET_ALL}")
            print(f"   Tenant: {notification.tenant_id}")
            print(f"   User: {notification.user_id}")
            print(f"   Type: {notification.type}")
            print(f"   Priority: {notification.priority.value}")
            print(f"   Channel: {Fore.YELLOW}{channel_record.channel}{Style.RESET_ALL}")
            print(f"   Provider: {channel_record.provider}")
            print(f"   Attempts: {channel_record.attempts}")

            # Show data (truncated for readability)
            if notification.data:
                print(f"\n   Data keys: {list(notification.data.keys())}")

                # Show recipient info
                email = notification.data.get('email')
                phone = notification.data.get('phone')
                slack_id = notification.data.get('slack_id')
                device_tokens = notification.data.get('device_tokens')

                if email:
                    print(f"   Email: {Fore.GREEN}{email}{Style.RESET_ALL}")
                if phone:
                    print(f"   Phone: {Fore.GREEN}{phone}{Style.RESET_ALL}")
                if slack_id:
                    print(f"   Slack ID: {Fore.GREEN}{slack_id}{Style.RESET_ALL}")
                if device_tokens:
                    print(f"   Device Tokens: {Fore.GREEN}{device_tokens}{Style.RESET_ALL}")

                # Show content
                subject = notification.data.get('subject', '')
                body = notification.data.get('body', '')
                if subject:
                    print(f"   Subject: {subject[:60]}...")
                if body:
                    print(f"   Body: {body[:100]}...")

            print("-" * 80)

        print(f"\n{Fore.YELLOW}These notifications are waiting to be processed by the worker.{Style.RESET_ALL}")
        print(f"\nTo process them, run: {Fore.CYAN}python run_worker.py{Style.RESET_ALL}\n")

if __name__ == "__main__":
    asyncio.run(check_queued())
