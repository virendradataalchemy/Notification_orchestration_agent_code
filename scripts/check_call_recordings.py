"""Check call recordings and their status."""

import asyncio
import sys
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.supabase import supabase_client


async def check_recordings():
    """Check all voice calls and their recording status."""
    
    print("=" * 80)
    print("CALL RECORDING STATUS CHECK")
    print("=" * 80)
    
    # Get all voice communications (channel_id = 2)
    communications = await supabase_client.select(
        "communications",
        "id,tenant_id,contact_id,notification_type,status,idempotency_key,recording_url,recording_duration,recording_sid,created_at,sent_at",
        filters={"channel_id": "eq.2", "order": "created_at.desc"}
    )
    
    if not communications:
        print("\n❌ No voice calls found in the database.")
        return
    
    print(f"\n📊 Found {len(communications)} voice call(s)\n")
    
    # Get contacts for names
    contacts = await supabase_client.select("contacts", "id,name,phone")
    contacts_by_id = {c["id"]: c for c in contacts}
    
    recorded_count = 0
    pending_count = 0
    no_recording_count = 0
    
    for comm in communications:
        contact = contacts_by_id.get(comm.get("contact_id"), {})
        contact_name = contact.get("name", "Unknown")
        contact_phone = contact.get("phone", "N/A")
        
        print("-" * 80)
        print(f"📞 Call ID: {comm['id']}")
        print(f"   Contact: {contact_name} ({contact_phone})")
        print(f"   Type: {comm.get('notification_type', 'N/A')}")
        print(f"   Status: {comm.get('status', 'N/A')}")
        print(f"   Created: {comm.get('created_at', 'N/A')}")
        print(f"   Call SID: {comm.get('idempotency_key', 'N/A')}")
        
        # Check recording status
        if comm.get('recording_url'):
            recorded_count += 1
            print(f"   ✅ RECORDING AVAILABLE")
            print(f"   📼 Recording SID: {comm.get('recording_sid', 'N/A')}")
            print(f"   🔗 Recording URL: {comm.get('recording_url', 'N/A')}")
            print(f"   ⏱️  Duration: {comm.get('recording_duration', 0)} seconds")
            print(f"   🎵 Play URL: {comm.get('recording_url', 'N/A')}.mp3")
        elif comm.get('status') in ['sent', 'delivered', 'completed']:
            pending_count += 1
            print(f"   ⏳ RECORDING PENDING (call completed, waiting for Twilio callback)")
            print(f"   💡 Tip: Recordings usually take 1-2 minutes after call ends")
        else:
            no_recording_count += 1
            print(f"   ⚠️  NO RECORDING (call status: {comm.get('status', 'unknown')})")
    
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"✅ Recorded: {recorded_count}")
    print(f"⏳ Pending: {pending_count}")
    print(f"⚠️  No Recording: {no_recording_count}")
    print(f"📊 Total Calls: {len(communications)}")
    
    # Show recent recording events
    print("\n" + "=" * 80)
    print("RECENT RECORDING EVENTS")
    print("=" * 80)
    
    events = await supabase_client.select(
        "notification_events",
        "id,communication_id,event_type,metadata,created_at",
        filters={"event_type": "eq.recording_completed", "order": "created_at.desc"}
    )
    
    if events:
        print(f"\n📝 Found {len(events)} recording event(s)\n")
        for event in events[:5]:  # Show last 5
            print(f"  • Communication ID: {event.get('communication_id')}")
            print(f"    Event: {event.get('event_type')}")
            print(f"    Time: {event.get('created_at')}")
            metadata = event.get('metadata', {})
            if metadata:
                print(f"    Recording SID: {metadata.get('recording_sid', 'N/A')}")
                print(f"    Duration: {metadata.get('recording_duration', 'N/A')} seconds")
            print()
    else:
        print("\n❌ No recording events found yet.")
        print("💡 This means Twilio hasn't sent any recording callbacks yet.")
    
    # Check webhook configuration
    print("\n" + "=" * 80)
    print("WEBHOOK CONFIGURATION CHECK")
    print("=" * 80)
    
    from src.config import settings
    
    if settings.app_base_url:
        print(f"✅ APP_BASE_URL configured: {settings.app_base_url}")
        print(f"   Voice Status Webhook: {settings.app_base_url}/api/webhooks/twilio/voice-status")
        print(f"   Recording Webhook: {settings.app_base_url}/api/webhooks/twilio/recording-status")
    else:
        print("⚠️  APP_BASE_URL not configured!")
        print("   Twilio cannot send recording callbacks without a public URL.")
        print("\n   To fix this:")
        print("   1. Install ngrok: https://ngrok.com/download")
        print("   2. Run: ngrok http 8000")
        print("   3. Add to .env: APP_BASE_URL=https://your-ngrok-url.ngrok.io")
        print("   4. Restart the server")


async def play_recording(communication_id: int):
    """Get playback instructions for a specific recording."""
    
    comm = await supabase_client.select(
        "communications",
        "id,recording_url,recording_duration,recording_sid",
        filters={"id": f"eq.{communication_id}"}
    )
    
    if not comm:
        print(f"❌ Communication {communication_id} not found")
        return
    
    comm = comm[0]
    
    if not comm.get('recording_url'):
        print(f"❌ No recording available for communication {communication_id}")
        return
    
    print("\n" + "=" * 80)
    print(f"RECORDING PLAYBACK - Communication {communication_id}")
    print("=" * 80)
    
    print(f"\n📼 Recording SID: {comm.get('recording_sid')}")
    print(f"⏱️  Duration: {comm.get('recording_duration')} seconds")
    print(f"\n🔗 Recording URLs:")
    print(f"   MP3: {comm.get('recording_url')}.mp3")
    print(f"   WAV: {comm.get('recording_url')}.wav")
    
    print(f"\n🎵 To play in browser:")
    print(f"   Open: {comm.get('recording_url')}.mp3")
    
    print(f"\n💾 To download:")
    print(f"   curl -u $TWILIO_ACCOUNT_SID:$TWILIO_AUTH_TOKEN \\")
    print(f"     '{comm.get('recording_url')}.mp3' \\")
    print(f"     -o recording_{communication_id}.mp3")
    
    print(f"\n🎧 HTML Audio Player:")
    print(f"   <audio controls>")
    print(f"     <source src=\"{comm.get('recording_url')}.mp3\" type=\"audio/mpeg\">")
    print(f"   </audio>")


async def main():
    """Main function."""
    
    if len(sys.argv) > 1:
        # Play specific recording
        try:
            comm_id = int(sys.argv[1])
            await play_recording(comm_id)
        except ValueError:
            print("❌ Invalid communication ID. Please provide a number.")
    else:
        # Check all recordings
        await check_recordings()


if __name__ == "__main__":
    asyncio.run(main())
