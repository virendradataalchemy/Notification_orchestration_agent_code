# Notification System API Endpoints

Base URL:

`http://ec2-65-2-190-203.ap-south-1.compute.amazonaws.com`

Authentication:

- All requests must include `X-API-Key`
- Use server-to-server integration only
- Do not call these endpoints directly from frontend or browser code

Common headers:

```http
X-API-Key: sk_live_demo_corp_GI4szPxNkI6RjHfgRzVezwMiqUzH0nFUrWM76nLyBlU
Content-Type: application/json
```

Supported channel values:

- `email`
- `sms`
- `whatsapp`
- `slack`
- `voice`

## 1. Create Raw Template

Endpoint:

```http
POST /api/v1/tenant/templates/
```

Purpose:

- Create and save a template directly using subject/body

Sample payload:

```json
{
  "name": "candidate_interview_email",
  "channel": "email",
  "language": "en",
  "subject": "Your interview is scheduled",
  "body": "Hi {{name}}, your interview is scheduled on {{interview_date}} at {{interview_time}}."
}
```

Optional fields:

```json
{
  "base_template_id": "global_template_id",
  "provider_template_ref": "twilio_content_sid",
  "provider_template_meta": {
    "category": "marketing"
  },
  "description": "Welcome email template",
  "branding": {
    "company_name": "DataAlchemy",
    "theme_color": "#2563eb",
    "contact_email": "support@dataalchemy.com",
    "website": "https://dataalchemy.com"
  }
}
```

Sample response:

```json
{
  "id": "demo_corp_candidate_i_email_abcd1234",
  "tenant_id": "demo_corp",
  "name": "candidate_interview_email",
  "channel": "email",
  "language": "en",
  "subject": "Your interview is scheduled",
  "body": "Hi {{name}}, your interview is scheduled on {{interview_date}} at {{interview_time}}.",
  "version": 1,
  "active": true,
  "is_global": false,
  "base_template_id": null,
  "provider_template_ref": null,
  "provider_template_meta": null,
  "branding": null,
  "created_at": "2026-05-20T10:21:38.784024"
}
```

## 2. Generate AI Single-Channel Draft

Endpoint:

```http
POST /api/v1/tenant/templates/ai-generate
```

Purpose:

- Generate a draft template from plain text or instructions
- This does not save the template

Sample payload:

```json
{
  "content": "Create a professional email template to inform a candidate that their interview is scheduled tomorrow at 11 AM.",
  "channel": "email"
}
```

Sample response:

```json
{
  "name": "suggested_template_name",
  "subject": "Your Interview is Scheduled",
  "body": "Hi {{name}}, your interview is scheduled for tomorrow at 11 AM.",
  "description": "AI generated email template"
}
```

Note:

- To get a real template ID, save the generated draft using `POST /api/v1/tenant/templates/`

## 3. Generate AI Multi-Channel Draft

Endpoint:

```http
POST /api/v1/tenant/templates/ai-generate-multi
```

Purpose:

- Generate draft templates for multiple channels at once
- This does not save the templates

Sample payload:

```json
{
  "content": "Inform the candidate that their interview is scheduled tomorrow at 11 AM.",
  "channels": ["email", "sms", "whatsapp"]
}
```

Sample response:

```json
{
  "templates": {
    "email": {
      "name": "interview_email",
      "subject": "Interview Scheduled",
      "body": "Hi {{name}}, your interview is scheduled for tomorrow at 11 AM.",
      "description": "AI generated email template"
    },
    "sms": {
      "name": "interview_sms",
      "subject": null,
      "body": "Hi {{name}}, your interview is tomorrow at 11 AM.",
      "description": "AI generated sms template"
    },
    "whatsapp": {
      "name": "interview_whatsapp",
      "subject": null,
      "body": "Hi {{name}}, your interview is tomorrow at 11 AM.",
      "description": "AI generated whatsapp template"
    }
  }
}
```

Note:

- Save each selected draft separately using `POST /api/v1/tenant/templates/`

## 4. Update Saved Template

Endpoint:

```http
PUT /api/v1/tenant/templates/{template_id}
```

Purpose:

- Update an existing saved template

Sample payload:

```json
{
  "subject": "Updated interview schedule",
  "body": "Hi {{name}}, your interview is scheduled on {{interview_date}}.",
  "description": "Updated version"
}
```

Other optional update fields:

```json
{
  "name": "new_template_name",
  "active": true,
  "provider_template_ref": "new_provider_ref",
  "provider_template_meta": {
    "category": "transactional"
  },
  "branding": {
    "company_name": "DataAlchemy",
    "theme_color": "#0f172a"
  }
}
```

## 5. List Templates

Endpoint:

```http
GET /api/v1/tenant/templates/
```

Purpose:

- List available tenant templates

Optional query parameters:

- `channel=email`
- `language=en`
- `include_global=true`

Sample response:

```json
{
  "tenant_id": "demo_corp",
  "templates": [
    {
      "id": "demo_corp_test_email_t_email_00643a68",
      "tenant_id": "demo_corp",
      "name": "test_email_template",
      "channel": "email",
      "language": "en",
      "subject": "Hello {{name}}",
      "body": "Hi {{name}}, this is a template test email.",
      "version": 1,
      "active": true,
      "is_global": false,
      "base_template_id": null,
      "provider_template_ref": null,
      "provider_template_meta": null,
      "branding": null,
      "created_at": "2026-05-20T10:21:38.784024"
    }
  ],
  "global_templates_count": 0,
  "tenant_templates_count": 1
}
```

## 6. Get Template Details

Endpoint:

```http
GET /api/v1/tenant/templates/{template_id}
```

Purpose:

- Fetch one saved template by its ID or template name

## 7A. Send Single Notification Using Template

Endpoint:

```http
POST /api/v1/notifications/send
```

Purpose:

- Send one notification to one recipient using a saved template

Sample payload:

```json
{
  "recipient": {
    "user_id": "candidate_001",
    "email": "arjun.rao@example.com"
  },
  "notification": {
    "type": "interview_email",
    "priority": "high",
    "channels": ["email"],
    "template_id": "demo_corp_candidate_i_email_abcd1234",
    "data": {
      "name": "Arjun",
      "interview_date": "2026-05-21",
      "interview_time": "11:00 AM"
    }
  }
}
```

## 7B. Send Single Notification Using Raw Subject and Body

Endpoint:

```http
POST /api/v1/notifications/send
```

Purpose:

- Send one notification to one recipient without using a saved template

Sample payload:

```json
{
  "recipient": {
    "user_id": "candidate_001",
    "email": "arjun.rao@example.com"
  },
  "notification": {
    "type": "interview_email",
    "priority": "high",
    "channels": ["email"],
    "subject": "Interview Reminder for {{name}}",
    "body": "Hi {{name}}, your interview is on {{interview_date}} at {{interview_time}}.",
    "data": {
      "name": "Arjun",
      "interview_date": "2026-05-21",
      "interview_time": "11:00 AM"
    }
  }
}
```

Note:

- For `email`, `sms`, `slack`, and `voice`, raw subject/body or raw body is allowed
- `whatsapp` requires template-based sending

## 8. Send Bulk Single-Channel Using Template

Endpoint:

```http
POST /api/v1/notifications/batch
```

Purpose:

- Send the same channel/template to multiple recipients

Sample payload:

```json
{
  "channel": "email",
  "template_id": "demo_corp_candidate_i_email_abcd1234",
  "recipients": [
    {
      "user_id": "candidate_001",
      "email": "arjun.rao@example.com",
      "data": {
        "name": "Arjun",
        "interview_date": "2026-05-21",
        "interview_time": "11:00 AM"
      }
    },
    {
      "user_id": "candidate_002",
      "email": "meera.iyer@example.com",
      "data": {
        "name": "Meera",
        "interview_date": "2026-05-21",
        "interview_time": "2:00 PM"
      }
    }
  ]
}
```

## 9. Send Bulk Multi-Channel Using Templates

Endpoint:

```http
POST /api/v1/notifications/batch-multichannel
```

Purpose:

- Send multiple channels in one request
- Different templates can be mapped per channel

Sample payload:

```json
{
  "channels": ["email", "sms"],
  "channel_template_map": {
    "email": "demo_corp_candidate_i_email_abcd1234",
    "sms": "demo_corp_candidate_i_sms_efgh5678"
  },
  "recipients": [
    {
      "user_id": "candidate_001",
      "email": "arjun.rao@example.com",
      "phone": "+91-9876543210",
      "data": {
        "name": "Arjun",
        "interview_date": "2026-05-21",
        "interview_time": "11:00 AM"
      }
    }
  ]
}
```

## 10. Check Notification Status

Endpoint:

```http
GET /api/v1/notifications/{notification_id}
```

Purpose:

- Fetch current status after send

## Important Notes

- `user_id` is required in all send payloads
- `email` is required for email sends
- `phone` is required for sms, whatsapp, and voice sends
- `whatsapp` requires a template-based flow
- `ai-generate` and `ai-generate-multi` return draft content only
- `POST /api/v1/tenant/templates/` returns the real saved template ID
- The deployed app is reachable and template creation is already verified live
- Notification send endpoints exist and are intended for this workflow
