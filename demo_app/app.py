import os
import uuid
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
import httpx
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Client Demo App")

ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_API_URL", "http://localhost:8000")
TENANT_ID = os.getenv("ORCHESTRATOR_TENANT_ID", "demo_corp")
API_KEY = os.getenv("ORCHESTRATOR_API_KEY", "sk_live_demo_corp_DPgrsArBLlQjzS-_FJuI7IzxOlkVT2cqtChFiDmlTa8")

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Notification Dispatcher</title>
    <style>
        body { font-family: 'Inter', sans-serif; background-color: #121212; color: #e0e0e0; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; padding: 20px;}
        .card { background: #1e1e1e; padding: 40px; border-radius: 12px; box-shadow: 0 10px 30px rgba(0,0,0,0.5); width: 600px; border: 1px solid #333; }
        h1 { color: #ffffff; text-align: center; margin-top: 0;}
        .section-title { font-size: 14px; text-transform: uppercase; color: #888; margin-bottom: 10px; border-bottom: 1px solid #333; padding-bottom: 5px; margin-top: 25px; letter-spacing: 1px;}
        .form-row { display: flex; gap: 15px; margin-bottom: 15px; }
        .form-group { flex: 1; text-align: left; }
        label { display: block; font-weight: 600; margin-bottom: 5px; color: #bbb; font-size: 13px; }
        input[type="text"], input[type="email"], select, textarea { width: 100%; padding: 12px; background: #2a2a2a; border: 1px solid #444; border-radius: 6px; box-sizing: border-box; color: #fff; font-family: inherit;}
        input:focus, select:focus, textarea:focus { border-color: #007bff; outline: none; }
        .checkbox-group { display: flex; gap: 15px; flex-wrap: wrap; margin-bottom: 20px;}
        .checkbox-label { display: flex; align-items: center; font-weight: normal; font-size: 14px; color: #ddd; cursor: pointer;}
        .checkbox-label input { margin-right: 8px; width: 16px; height: 16px; accent-color: #007bff; }
        button { background-color: #007bff; color: white; border: none; padding: 14px 20px; border-radius: 6px; cursor: pointer; font-size: 16px; font-weight: bold; width: 100%; transition: background 0.2s;}
        button:hover { background-color: #0056b3; }
        .success { background-color: rgba(40, 167, 69, 0.2); color: #4caf50; padding: 15px; border-radius: 6px; margin-bottom: 20px; border: 1px solid rgba(40, 167, 69, 0.4); }
        .error { background-color: rgba(220, 53, 69, 0.2); color: #ff5252; padding: 15px; border-radius: 6px; margin-bottom: 20px; border: 1px solid rgba(220, 53, 69, 0.4); }
        code { background: #000; padding: 2px 6px; border-radius: 4px; font-family: monospace; color: #00ffaa;}
    </style>
</head>
<body>
    <div class="card">
        <h1>Orchestrator Control Panel</h1>
        <p style="text-align: center; color: #999; font-size: 14px; margin-bottom: 30px;">Directly feed inputs into the background orchestration system.</p>
        
        {message}

        <form action="/dispatch" method="post">
            
            <div class="section-title">1. Recipient Details</div>
            <div class="form-row">
                <div class="form-group">
                    <label>User ID</label>
                    <input type="text" name="user_id" value="usr_839210" required>
                </div>
                <div class="form-group">
                    <label>Email Address</label>
                    <input type="email" name="email" value="Virendra.Kumar@dataalchemy.ai">
                </div>
                <div class="form-group">
                    <label>Phone / SMS</label>
                    <input type="text" name="phone" value="+15551234567">
                </div>
            </div>

            <div class="section-title">2. Notification Settings</div>
            <div class="form-row">
                <div class="form-group">
                    <label>Notification Type</label>
                    <input type="text" name="notif_type" value="system_alert" required placeholder="e.g. order_update, system_alert">
                </div>
                <div class="form-group">
                    <label>Priority</label>
                    <select name="priority">
                        <option value="critical">CRITICAL</option>
                        <option value="high" selected>HIGH</option>
                        <option value="medium">MEDIUM</option>
                        <option value="low">LOW</option>
                    </select>
                </div>
            </div>

            <label style="margin-top: 15px;">Target Channels (Checked = Requested)</label>
            <div class="checkbox-group">
                <label class="checkbox-label"><input type="checkbox" name="channels" value="email" checked> Email</label>
                <label class="checkbox-label"><input type="checkbox" name="channels" value="sms"> SMS</label>
                <label class="checkbox-label"><input type="checkbox" name="channels" value="slack"> Slack</label>
                <label class="checkbox-label"><input type="checkbox" name="channels" value="whatsapp"> WhatsApp</label>
            </div>

            <div class="section-title">3. Payload Data</div>
            <div class="form-group">
                <label>Subject / Title</label>
                <input type="text" name="subject" value="System Test Ping" required>
            </div>
            <div class="form-group">
                <label>Dynamic Body Content</label>
                <textarea name="body" rows="4" required>Hello, this is a direct test message routed through the orchestration logic framework.</textarea>
            </div>

            <button type="submit" style="margin-top: 20px;">⚡ Dispatch Notification</button>
        </form>
    </div>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
async def home(request: Request, msg: str = None, success: str = None):
    message_html = ""
    if msg:
        if success == 'true':
            message_html = f"<div class='success'><strong>Dispatch Success!</strong><br>{msg}</div>"
        else:
            message_html = f"<div class='error'><strong>Dispatch Failed:</strong><br>{msg}</div>"

    return HTML_TEMPLATE.format(message=message_html)

@app.post("/dispatch", response_class=HTMLResponse)
async def dispatch_notification(
    user_id: str = Form(...), 
    email: str = Form(None), 
    phone: str = Form(None),
    notif_type: str = Form(...),
    priority: str = Form(...),
    channels: list[str] = Form(...),
    subject: str = Form(...),
    body: str = Form(...)
):
    
    # Trigger notification via Orchestrator
    payload = {
        "recipient": {
            "user_id": user_id,
            "email": email,
            "phone": phone
        },
        "notification": {
            "type": notif_type,
            "priority": priority,
            "channels": channels,
            "data": {
                "subject": subject,
                "body": body
            }
        }
    }

    headers = {
        "X-API-Key": API_KEY,
        "X-Tenant-Id": TENANT_ID,
        "Content-Type": "application/json"
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{ORCHESTRATOR_URL}/api/v1/notifications/send",
                json=payload,
                headers=headers,
                timeout=10.0
            )

            if response.status_code in [200, 201, 202]:
                data = response.json()
                nid = data.get('notification_id', 'Unknown')
                return await home(None, f"Orchestrator accepted the payload.<br>Tracking ID: <code>{nid}</code>", 'true')
            else:
                return await home(None, f"Orchestrator rejected with: {response.text}", 'false')
            
    except Exception as e:
        return await home(None, f"Failed to connect to Orchestrator at {ORCHESTRATOR_URL}. Is it running?<br>Error: {str(e)}", 'false')

if __name__ == "__main__":
    import uvicorn
    # Make sure we don't conflict with Orchestrator (8000)
    uvicorn.run(app, host="0.0.0.0", port=5000)
