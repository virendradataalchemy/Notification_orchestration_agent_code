"""
Live Demo Notification Sender - Fully Corrected Version
"""

import os
import sys
import asyncio
import httpx
from datetime import datetime
from dotenv import load_dotenv
import json
from colorama import init, Fore, Style
import time

# Initialize colorama for colored output
init(autoreset=True)

# Load environment variables
load_dotenv()

# Configuration
API_BASE_URL = os.getenv("DEMO_API_URL", "http://localhost:8000")
API_KEY = "sk_live_demo_corp_m1UxVyIM67QKaSxTTGYqg244DObbChfZ78Te09o7Wy0"
TENANT_ID = os.getenv("TENANT_ID", "demo_corp")

# --- UI Helpers ---

def print_header(text):
    print("\n" + "=" * 70)
    print(f"{Fore.CYAN}{Style.BRIGHT}{text.center(70)}{Style.RESET_ALL}")
    print("=" * 70)

def print_success(text):
    print(f"{Fore.GREEN}✓ {text}{Style.RESET_ALL}")

def print_info(text):
    print(f"{Fore.BLUE}ℹ {text}{Style.RESET_ALL}")

def print_warning(text):
    print(f"{Fore.YELLOW}⚠ {text}{Style.RESET_ALL}")

def print_error(text):
    print(f"{Fore.RED}✗ {text}{Style.RESET_ALL}")

# --- Core Logic ---

async def send_request(client: httpx.AsyncClient, endpoint: str, payload: dict, demo_name: str):
    """Generic helper to send POST requests with correct headers."""
    print_info(f"Sending {demo_name}...")
    
    headers = {
        "X-API-Key": API_KEY,
        "X-Tenant-Id": TENANT_ID,
        "Content-Type": "application/json"
    }

    try:
        response = await client.post(
            f"{API_BASE_URL}{endpoint}",
            json=payload,
            headers=headers,
            timeout=30.0
        )

        if response.status_code in [200, 201, 202]:
            data = response.json()
            print_success(f"{demo_name} sent successfully!")
            
            # Extract ID based on response type (single vs batch)
            res_id = data.get('notification_id') or data.get('batch_id')
            print(f"   ID: {Fore.YELLOW}{res_id}{Style.RESET_ALL}")
            print(f"   Status: {Fore.GREEN}{data.get('status')}{Style.RESET_ALL}")
            return data
        else:
            print_error(f"Failed: {response.status_code}")
            print(f"   Response: {response.text}")
            return None
    except Exception as e:
        print_error(f"Request Error: {str(e)}")
        return None

# --- Demo Functions ---

async def demo_1_simple_email(client: httpx.AsyncClient):
    print_header("DEMO 1: Simple Email Notification")
    payload = {
        "recipient": {"user_id": "demo_user_001", "email": "Virendra.Kumar@dataalchemy.ai"},
        "notification": {
            "type": "order_confirmation",
            "priority": "high",
            "channels": ["email"],
            "template_id": "order_confirm_email",
            "data": {
                "customer_name": "Alice Johnson",
                "order_id": f"ORD-{int(time.time())}",
                "total": "$129.99"
            }
        }
    }
    return await send_request(client, "/api/v1/notifications/send", payload, "Simple Email")

async def demo_2_multi_channel(client: httpx.AsyncClient):
    print_header("DEMO 2: Multi-Channel (Email + SMS)")
    payload = {
        "recipient": {
            "user_id": "demo_user_002",
            "email": "Virendra.Kumar@dataalchemy.ai",
            "phone": "+13509308394"
        },
        "notification": {
            "type": "order_confirmation",
            "channels": ["email", "sms"],
            "data": {"customer_name": "Bob Smith", "total": "$249.99"}
        }
    }
    return await send_request(client, "/api/v1/notifications/send", payload, "Multi-Channel")

async def demo_5_batch_notifications(client: httpx.AsyncClient):
    print_header("DEMO 5: Batch Notifications")
    payload = {
        "template_id": "welcome_email",
        "recipients": [
            {"user_id": "u1", "email": "alice@test.com", "data": {"customer_name": "Alice"}},
            {"user_id": "u2", "email": "bob@test.com", "data": {"customer_name": "Bob"}}
        ],
        "channel": "email"
    }
    # FIXED: Now uses the shared helper with X-API-Key and X-Tenant-Id
    return await send_request(client, "/api/v1/notifications/batch", payload, "Batch Send")

# --- Execution ---

async def run_all_demos():
    print_header("🎬 LIVE NOTIFICATION DEMO")
    
    async with httpx.AsyncClient() as client:
        # 1. Health Check
        try:
            health = await client.get(f"{API_BASE_URL}/health")
            if health.status_code != 200:
                print_error("API is unhealthy. Check server.")
                return
        except Exception:
            print_error("Cannot connect to API.")
            return

        input(f"\n{Fore.YELLOW}Press Enter to start sequence...{Style.RESET_ALL}")

        results = []
        demo_funcs = [
            ("Demo 1", demo_1_simple_email),
            ("Demo 2", demo_2_multi_channel),
            ("Demo 5", demo_5_batch_notifications)
        ]

        for name, func in demo_funcs:
            res = await func(client)
            if res and isinstance(res, dict):
                results.append((name, res))
            await asyncio.sleep(1.5)

        # 2. Final Summary
        print_header("📊 DEMO SUMMARY")
        print(f"\n{Fore.GREEN}Successfully processed {len(results)} demos!{Style.RESET_ALL}\n")
        for name, data in results:
            rid = data.get('notification_id') or data.get('batch_id') or "N/A"
            print(f"   ✓ {name}: {rid}")

if __name__ == "__main__":
    asyncio.run(run_all_demos())