# 📦 DEMO PACKAGE SUMMARY - ALL FIXED!


# 2. Start services (2 terminals)
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
celery -A src.celery_app worker --loglevel=info -P solo




```bash
python demo_send_notifications.py
```


# 2. Create tenant
python scripts/create_tenant.py --tenant-id "demo_corp" --name "Demo Corporation" --email "admin@democorp.com"
# ⚠️ SAVE THE API KEY!

# 3. Add to .env file (replace YOUR_KEY with actual key)
echo 'API_KEY=sk_live_demo_corp_YOUR_KEY' >> .env
echo 'TENANT_ID=demo_corp' >> .env
echo 'DEMO_API_URL=http://localhost:8000' >> .env



# === START SERVICES (Keep running) ===

# Terminal 1: API Server
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2: Worker
celery -A src.celery_app worker --loglevel=info -P solo

# === RUN DEMO ===

# Terminal 3: Demo script
python demo_send_notifications.py
```

---

## 📊 DEMO SCRIPT OUTPUT PREVIEW

```
======================================================================
                    🎬 LIVE NOTIFICATION DEMO
======================================================================

Configuration:
   API URL: http://localhost:8000
   API Key: sk_live_demo_corp_v8n3k...
   Tenant: demo_corp

ℹ Testing connection to API...
✓ API is healthy! {'status': 'healthy'}

Ready to send notifications!

Press Enter to start...

======================================================================
             DEMO 1: Simple Email Notification
======================================================================

ℹ Sending order confirmation email to Alice Johnson...
✓ Order Confirmation Email sent successfully!
   Notification ID: 123e4567-e89b-12d3-a456-426614174000
   Status: queued
   Channels: email

💡 What happened:
   • One API call sent an email
   • Template variables replaced
   • Open and click tracking enabled

[... 4 more demos ...]

======================================================================
                         📊 DEMO SUMMARY
======================================================================

Successfully sent 5 notifications!

View Results:
   Admin Dashboard: http://localhost:8000/dashboard
   Tenant Dashboard: http://localhost:8000/tenant-dashboard

🎉 Demo complete!
```

---

## 💡 DEMO TIPS

### Before Demo:
1. ✅ Test script once: `python demo_send_notifications.py --demo 1`
2. ✅ Open browser tabs (dashboard, tenant dashboard)
3. ✅ Have backup ready (Swagger UI at /api/v1/docs)

### During Demo:
1. ✅ Keep terminal visible so client sees code
2. ✅ Let script run, talk through what's happening
3. ✅ Point to colored output
4. ✅ After script, switch to dashboard

### After Demo:
1. ✅ Send follow-up email within 4 hours
2. ✅ Include POC agreement
3. ✅ Schedule next meeting

---

