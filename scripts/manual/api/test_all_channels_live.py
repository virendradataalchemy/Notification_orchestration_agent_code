"""
Live Test Script for ALL Notification Channels
Corrected to match provider-specific payload requirements.
"""

import os
import sys
import asyncio
import httpx
from datetime import datetime
from dotenv import load_dotenv
from colorama import init, Fore, Style
import time

# Initialize colorama
init(autoreset=True)

# Load environment variables
load_dotenv()

# Configuration
API_BASE_URL = os.getenv("DEMO_API_URL", "http://localhost:8000")
API_KEY = os.getenv("API_KEY", "sk_live_demo_corp_m1UxVyIM67QKaSxTTGYqg244DObbChfZ78Te09o7Wy0")
TENANT_ID = os.getenv("TENANT_ID", "demo_corp")

# Real recipient details from .env
# FIX: Ensure these are clean strings
TEST_EMAIL = os.getenv("AWS_SES_FROM_EMAIL", "virendra.kumar@dataalchemy.ai")
TEST_PHONE = os.getenv("TEST_RECEIVER_PHONE", "+13509308394") # Use your real phone here
TEST_WHATSAPP_PHONE = os.getenv("TEST_RECEIVER_WHATSAPP_PHONE", "+14155238886") # Use your real phone here
TEST_SLACK_CHANNEL = os.getenv("SLACK_CHANNEL_ID", "C0AMWSS3FK2")

# UI Helpers
def print_header(text):
    print("\n" + "=" * 80)
    print(f"{Fore.CYAN}{Style.BRIGHT}{text.center(80)}{Style.RESET_ALL}")
    print("=" * 80)

def print_success(text):
    print(f"{Fore.GREEN}✓ {text}{Style.RESET_ALL}")

def print_info(text):
    print(f"{Fore.BLUE}ℹ {text}{Style.RESET_ALL}")

def print_warning(text):
    print(f"{Fore.YELLOW}⚠ {text}{Style.RESET_ALL}")

def print_error(text):
    print(f"{Fore.RED}✗ {text}{Style.RESET_ALL}")

async def send_notification(client: httpx.AsyncClient, channel: str, payload: dict, test_name: str):
    headers = {
        "X-API-Key": API_KEY,
        "X-Tenant-Id": TENANT_ID,
        "Content-Type": "application/json"
    }

    try:
        response = await client.post(
            f"{API_BASE_URL}/api/v1/notifications/send",
            json=payload,
            headers=headers,
            timeout=30.0
        )

        if response.status_code in [200, 201, 202]:
            data = response.json()
            nid = data.get('notification_id', 'N/A')
            print_success(f"{test_name} Queued. ID: {nid}")
            return {"success": True, "channel": channel, "id": nid}
        else:
            print_error(f"{test_name} Failed: {response.text}")
            return {"success": False, "channel": channel, "error": response.text}
    except Exception as e:
        print_error(f"{test_name} Error: {str(e)}")
        return {"success": False, "channel": channel, "error": str(e)}

# --- Channel Tests ---

async def test_email(client):
    print_header("TEST 1: EMAIL")
    payload = {
        "recipient": {"user_id": "user_1", "email": TEST_EMAIL},
        "notification": {
            "type": "alert",
            "priority": "high",
            "channels": ["email"],
            "data": {
                "subject": "Critical System Update",
                "body": "This is a test email content required by Mailgun/SES.",
                "customer_name": "Virendra"
            }
        }
    }
    return await send_notification(client, "EMAIL", payload, "Email")

async def test_sms(client):
    print_header("TEST 2: SMS")
    payload = {
        "recipient": {"user_id": "user_1", "phone": TEST_PHONE},
        "notification": {
            "type": "alert",
            "priority": "high",
            "channels": ["sms"],
            "data": {
                "body": f"Your SMS verification code is {int(time.time()) % 10000}. This body is required."
            }
        }
    }
    return await send_notification(client, "SMS", payload, "SMS")

async def test_whatsapp(client):
    print_header("TEST 3: WHATSAPP")
    payload = {
        "recipient": {"user_id": "user_1", "phone": TEST_WHATSAPP_PHONE},
        "notification": {
            "type": "alert",
            "priority": "medium",
            "channels": ["whatsapp"],
            "data": {
                "body": "Hello from Notification Orchestrator! WhatsApp requires this body field."
            }
        }
    }
    return await send_notification(client, "WHATSAPP", payload, "WhatsApp")

async def test_slack(client):
    print_header("TEST 4: SLACK")
    payload = {
        "recipient": {"user_id": "user_1", "slack_id": TEST_SLACK_CHANNEL}, # Key must be slack_id
        "notification": {
            "type": "alert",
            "priority": "medium",
            "channels": ["slack"],
            "data": {
                "title": "Slack Alert",
                "body": "New deployment successful in Noida DC.",
                "url": "https://dataalchemy.ai"
            }
        }
    }
    return await send_notification(client, "SLACK", payload, "Slack")

async def test_push(client):
    print_header("TEST 5: PUSH")
    payload = {
        "recipient": {
            "user_id": "user_1", 
            "device_tokens": ["fcm_token_123"] # Key must match your worker's expectation
        },
        "notification": {
            "type": "alert",
            "priority": "high",
            "channels": ["push"],
            "data": {
                "title": "Push Test",
                "body": "This body is displayed in the notification tray.",
                "click_action": "https://localhost:8000"
            }
        }
    }
    return await send_notification(client, "PUSH", payload, "Push")

async def test_voice(client):
    print_header("TEST 6: VOICE")
    payload = {
        "recipient": {"user_id": "user_1", "phone": TEST_PHONE},
        "notification": {
            "type": "alert",
            "priority": "critical",
            "channels": ["voice"],
            "data": {
                "message": "This is a critical voice alert from your AI Agent. Please check the dashboard.",
                "voice": "Polly.Amy",
                "language": "en-GB"
            }
        }
    }
    return await send_notification(client, "VOICE", payload, "Voice")

async def test_inapp(client):
    print_header("TEST 7: IN-APP")
    payload = {
        "recipient": {"user_id": "test_user_virendra"},
        "notification": {
            "type": "test",
            "priority": "low",
            "channels": ["inapp"],
            "data": {
                "title": "Welcome!",
                "message": "In-app notification is working correctly."
            }
        }
    }
    return await send_notification(client, "INAPP", payload, "In-App")

async def run_all_channel_tests():
    print_header("STARTING LIVE CHANNEL AUDIT")
    async with httpx.AsyncClient() as client:
        results = []
        test_funcs = [test_email, test_sms, test_whatsapp, test_slack, test_push, test_voice, test_inapp]
        
        for func in test_funcs:
            results.append(await func(client))
            await asyncio.sleep(1)

        print_header("📊 FINAL AUDIT SUMMARY")
        for r in results:
            icon = f"{Fore.GREEN}✓" if r["success"] else f"{Fore.RED}✗"
            print(f"{icon} {r['channel']:<10} | {r.get('id', 'FAILED')}")

if __name__ == "__main__":
    asyncio.run(run_all_channel_tests())