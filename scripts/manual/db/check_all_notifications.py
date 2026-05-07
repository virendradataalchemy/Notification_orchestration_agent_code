"""
Check ALL recent notifications in the database
"""

import asyncio
from sqlalchemy import select, desc
from src.core.database import AsyncSessionLocal
from src.models import Notification, NotificationChannel
from colorama import init, Fore, Style
from datetime import datetime, timedelta

init(autoreset=True)

async def check_all():
    """Check all recent notifications."""
    print("\n" + "=" * 80)
    print(f"{Fore.CYAN}{Style.BRIGHT}{'ALL RECENT NOTIFICATIONS'.center(80)}{Style.RESET_ALL}")
    print("=" * 80 + "\n")

    async with AsyncSessionLocal() as db:
        # Get recent notifications (last 24 hours)
        cutoff_time = datetime.utcnow() - timedelta(hours=24)

        query = (
            select(Notification)
            .where(Notification.created_at >= cutoff_time)
            .order_by(desc(Notification.created_at))
            .limit(20)
        )

        result = await db.execute(query)
        notifications = result.scalars().all()

        if not notifications:
            print(f"{Fore.YELLOW}No notifications found in the last 24 hours.{Style.RESET_ALL}")
            return

        print(f"Found {Fore.GREEN}{len(notifications)}{Style.RESET_ALL} notifications:\n")

        for i, notification in enumerate(notifications, 1):
            # Get channels for this notification
            channel_query = select(NotificationChannel).where(
                NotificationChannel.notification_id == notification.id
            )
            channel_result = await db.execute(channel_query)
            channels = channel_result.scalars().all()

            status_color = Fore.GREEN if notification.status.value == "sent" or notification.status.value == "delivered" else Fore.RED if notification.status.value == "failed" else Fore.YELLOW

            print(f"{Fore.CYAN}#{i} {notification.id}{Style.RESET_ALL}")
            print(f"   Status: {status_color}{notification.status.value.upper()}{Style.RESET_ALL}")
            print(f"   Tenant: {notification.tenant_id}")
            print(f"   User: {notification.user_id}")
            print(f"   Type: {notification.type}")
            print(f"   Priority: {notification.priority.value}")
            print(f"   Created: {notification.created_at}")

            if channels:
                print(f"\n   Channels:")
                for channel in channels:
                    ch_status_color = Fore.GREEN if channel.status.value == "sent" or channel.status.value == "delivered" else Fore.RED if channel.status.value == "failed" else Fore.YELLOW

                    print(f"      - {channel.channel}: {ch_status_color}{channel.status.value}{Style.RESET_ALL}")
                    print(f"        Provider: {channel.provider}")
                    print(f"        Attempts: {channel.attempts}")

                    if channel.error_message:
                        print(f"        Error: {Fore.RED}{channel.error_message[:100]}{Style.RESET_ALL}")

                    if channel.message_id:
                        print(f"        Message ID: {channel.message_id[:50]}")

            # Show recipient info from data
            if notification.data:
                email = notification.data.get('email')
                phone = notification.data.get('phone')
                slack_id = notification.data.get('slack_id')

                if email:
                    print(f"   Recipient Email: {email}")
                if phone:
                    print(f"   Recipient Phone: {phone}")
                if slack_id:
                    print(f"   Recipient Slack: {slack_id}")

            print("-" * 80)

if __name__ == "__main__":
    asyncio.run(check_all())
