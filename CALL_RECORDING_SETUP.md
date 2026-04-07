# Call Recording Setup Guide

This guide explains how to enable and use call recording for voice notifications.

## Features

- ✅ Automatic call recording for all voice calls
- ✅ Dual-channel recording (both caller and recipient)
- ✅ Recording URLs stored in database
- ✅ Webhook callbacks from Twilio
- ✅ Recording duration tracking
- ✅ Easy playback and download

## Setup Steps

### 1. Update Database Schema

Run the SQL migration in your Supabase SQL editor:

```bash
# File: scripts/add_call_recording_fields.sql
```

This adds three new columns to the `communications` table:
- `recording_url` - URL to access the recording
- `recording_duration` - Duration in seconds
- `recording_sid` - Twilio recording identifier

### 2. Configure Webhook URL

You need to set your public webhook URL in the `.env` file:

```env
APP_BASE_URL=https://yourdomain.com
```

For local development with ngrok:
```bash
ngrok http 8000
# Copy the https URL (e.g., https://abc123.ngrok.io)
```

Then update `.env`:
```env
APP_BASE_URL=https://abc123.ngrok.io
```

### 3. Restart the Backend

The server will automatically reload with the new configuration.

## How It Works

### 1. Making a Call with Recording

When you send a voice notification, recording is enabled by default:

```python
# Recording is enabled automatically
await notification_service.send_notification(
    tenant_id=1,
    payload={
        "contact_id": 1,
        "notification_type": "voice_call",
        "channels": ["voice"],
        "data": {
            "name": "John",
            "message": "Hello, this is a test call"
        }
    }
)
```

To disable recording for a specific call:

```python
await notification_service.send_notification(
    tenant_id=1,
    payload={
        "contact_id": 1,
        "notification_type": "voice_call",
        "channels": ["voice"],
        "data": {
            "name": "John",
            "message": "Hello, this is a test call",
            "record_call": False  # Disable recording
        }
    }
)
```

### 2. Webhook Flow

1. **Call Initiated**: Twilio starts the call
2. **Call Completed**: Twilio ends the call and starts recording processing
3. **Recording Ready**: Twilio sends webhook to `/api/webhooks/twilio/recording-status`
4. **Database Updated**: Recording URL and duration are saved

### 3. Accessing Recordings

#### Via API

```bash
# Get recording by SID
GET /api/webhooks/twilio/recording/{recording_sid}

Response:
{
  "recording_sid": "RE...",
  "recording_url": "https://api.twilio.com/...",
  "recording_duration": 45
}
```

#### Via Database Query

```sql
SELECT 
  id,
  contact_id,
  notification_type,
  recording_url,
  recording_duration,
  created_at
FROM communications
WHERE recording_url IS NOT NULL
ORDER BY created_at DESC;
```

#### Direct Playback

The `recording_url` from Twilio can be used directly in an audio player:

```html
<audio controls>
  <source src="{recording_url}.mp3" type="audio/mpeg">
</audio>
```

## Recording Details

### Recording Format
- **Channels**: Dual (both sides of the conversation)
- **Format**: MP3 or WAV (Twilio default)
- **Quality**: Standard telephony quality
- **Storage**: Stored on Twilio's servers

### Recording URL Format

Twilio provides URLs in this format:
```
https://api.twilio.com/2010-04-01/Accounts/{AccountSid}/Recordings/{RecordingSid}
```

To get the audio file, append the format:
- `.mp3` for MP3 format
- `.wav` for WAV format

Example:
```
https://api.twilio.com/2010-04-01/Accounts/AC.../Recordings/RE....mp3
```

### Recording Retention

- Twilio stores recordings for a configurable period (default: indefinitely)
- You can configure auto-deletion in Twilio console
- Recommended: Download and store important recordings in your own storage

## Security Considerations

### 1. Webhook Authentication

The webhooks are currently open. For production, add Twilio signature validation:

```python
from twilio.request_validator import RequestValidator

validator = RequestValidator(settings.twilio_auth_token)

def validate_twilio_request(request: Request):
    signature = request.headers.get('X-Twilio-Signature', '')
    url = str(request.url)
    params = await request.form()
    
    if not validator.validate(url, params, signature):
        raise HTTPException(status_code=403, detail="Invalid signature")
```

### 2. Recording Access Control

- Recording URLs require Twilio authentication
- Implement access control in your application
- Consider downloading and storing recordings in your own secure storage

### 3. Compliance

- **GDPR**: Inform users about call recording
- **TCPA**: Get consent before recording
- **State Laws**: Some states require two-party consent
- **Data Retention**: Implement appropriate retention policies

## Testing

### 1. Test Call with Recording

```bash
# Send a test voice notification
curl -X POST http://localhost:8000/api/v1/notifications/demo/send \
  -H "Content-Type: application/json" \
  -H "X-Tenant-Id: 1" \
  -d '{
    "contact_id": 1,
    "notification_type": "test_call",
    "channels": ["voice"],
    "data": {
      "name": "Test User",
      "message": "This is a test call with recording"
    }
  }'
```

### 2. Check Recording Status

After the call completes (usually 1-2 minutes):

```bash
# Query the database
SELECT recording_url, recording_duration 
FROM communications 
WHERE id = {communication_id};
```

### 3. Play Recording

Use the recording URL in a browser or audio player.

## Troubleshooting

### Recording Not Saved

1. **Check webhook URL**: Ensure `APP_BASE_URL` is publicly accessible
2. **Check Twilio logs**: Go to Twilio Console > Monitor > Logs
3. **Check application logs**: Look for webhook callback errors
4. **Verify database**: Ensure migration was run successfully

### Webhook Not Received

1. **Test webhook URL**: 
   ```bash
   curl https://yourdomain.com/api/webhooks/twilio/recording-status
   ```
2. **Check firewall**: Ensure port 8000 (or your port) is open
3. **Use ngrok**: For local testing, use ngrok to expose your local server

### Recording URL Not Working

1. **Check Twilio credentials**: Ensure they're valid
2. **Add format extension**: Append `.mp3` or `.wav` to the URL
3. **Check Twilio account**: Verify recordings are enabled in your account

## Advanced Features

### Custom Recording Storage

To download and store recordings in your own storage (S3, etc.):

```python
import httpx
from src.config import settings

async def download_recording(recording_url: str, recording_sid: str):
    """Download recording from Twilio and store in S3."""
    
    # Download from Twilio
    auth = (settings.twilio_account_sid, settings.twilio_auth_token)
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{recording_url}.mp3", auth=auth)
        audio_data = response.content
    
    # Upload to S3
    s3_key = f"recordings/{recording_sid}.mp3"
    # ... upload to S3 ...
    
    return s3_url
```

### Recording Transcription

Integrate with speech-to-text services:

```python
from google.cloud import speech

async def transcribe_recording(recording_url: str):
    """Transcribe call recording using Google Speech-to-Text."""
    
    # Download audio
    audio_data = await download_recording(recording_url)
    
    # Transcribe
    client = speech.SpeechClient()
    audio = speech.RecognitionAudio(content=audio_data)
    config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.MP3,
        language_code="en-US",
    )
    
    response = client.recognize(config=config, audio=audio)
    
    return response.results[0].alternatives[0].transcript
```

## API Reference

### POST /api/webhooks/twilio/voice-status

Receives call status updates from Twilio.

**Parameters:**
- `CallSid`: Twilio call identifier
- `CallStatus`: Current call status
- `CallDuration`: Call duration in seconds

### POST /api/webhooks/twilio/recording-status

Receives recording completion notifications from Twilio.

**Parameters:**
- `CallSid`: Twilio call identifier
- `RecordingSid`: Twilio recording identifier
- `RecordingUrl`: URL to access the recording
- `RecordingDuration`: Recording duration in seconds
- `RecordingStatus`: Recording status (completed, etc.)

### GET /api/webhooks/twilio/recording/{recording_sid}

Retrieves recording information by SID.

**Response:**
```json
{
  "recording_sid": "RE...",
  "recording_url": "https://api.twilio.com/...",
  "recording_duration": 45
}
```

## Support

For issues or questions:
1. Check Twilio documentation: https://www.twilio.com/docs/voice/tutorials/how-to-record-phone-calls
2. Review application logs
3. Test webhooks with Twilio's webhook debugger
