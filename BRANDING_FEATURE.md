# Email Branding Feature

## Overview

All emails sent through the notification system now automatically include a branded footer with your company logo and contact information.

## Features

- ✅ Automatic branding footer on ALL emails (with or without templates)
- ✅ Company logo display
- ✅ Contact information (phone, email, website)
- ✅ Customizable theme colors
- ✅ Optional custom HTML footer

## Configuration

### Database Table: `tenant_branding`

Stores branding configuration per tenant:
- `logo_url` - Public URL to company logo
- `company_name` - Company name
- `theme_color` - Brand color (hex code)
- `contact_email` - Contact email
- `contact_phone` - Contact phone
- `website` - Company website
- `footer_html` - Optional custom HTML template
- `enabled` - Enable/disable branding

### Managing Branding

Use the debug script to check current configuration:
```bash
python debug_branding.py
```

Update branding via the template editor UI or directly in the database.

## How It Works

1. **Email without template**: System calls `render_raw_content()` which automatically appends branding footer
2. **Email with template**: System calls `render_template()` which automatically appends branding footer
3. **Footer generation**: `render_branding_footer_html()` creates HTML with logo and contact info
4. **Email delivery**: Complete HTML (content + footer) is sent via email provider

## Footer Structure

```
─────────────────────────────────
[Logo Image]  Company Name
              M: Phone
              E: Email
              W: Website
─────────────────────────────────
```

## Code Changes

### Modified Files

1. **src/services/notification_service.py**
   - Added branding rendering for single notifications (line ~540)
   - Added branding rendering for batch notifications (line ~760)
   - Added branding rendering for batch multichannel (line ~970)

2. **src/services/tenant_template_engine.py**
   - `render_raw_content()` - Renders content without template + branding
   - `render_branding_footer_html()` - Generates footer HTML
   - `_default_email_branding_footer()` - Default footer layout

3. **src/models/tenant_branding.py**
   - Database model for branding configuration

4. **src/api/routers/branding.py**
   - API endpoints for managing branding

## Best Practices

### Logo URL
- Use public URLs (not base64) for better email client compatibility
- Recommended hosting: AWS S3, Cloudinary, CDN
- Optimal size: 120px width, maintain aspect ratio

### Email Authentication
For production, configure:
- SPF record: `v=spf1 include:mailgun.org ~all`
- DKIM: Get from Mailgun dashboard
- DMARC: `v=DMARC1; p=none; rua=mailto:postmaster@yourdomain.com`

This ensures email clients display images automatically.

## Troubleshooting

### Logo not showing in Gmail
- **Cause**: Gmail blocks external images from unverified senders
- **Solution**: Click "Display images below" in Gmail
- **Production fix**: Set up email authentication (SPF, DKIM, DMARC)

### Branding not applied
- Check if branding is enabled: `SELECT enabled FROM tenant_branding WHERE tenant_id = 'your_tenant'`
- Verify logo_url is set
- Check server logs for rendering errors

### Logo URL not accessible
- Test URL in browser
- Ensure URL is publicly accessible (not behind authentication)
- Check CORS settings if using CDN

## API Usage

### Send email with automatic branding
```python
POST /api/v1/notifications/send
{
  "recipient": {
    "user_id": "user_123",
    "email": "user@example.com"
  },
  "notification": {
    "type": "notification",
    "priority": "high",
    "channels": ["email"],
    "subject": "Your Subject",
    "body": "<p>Your content</p>"
  }
}
```

The branding footer is automatically appended - no additional configuration needed.

## Summary

- ✅ Branding applies to all emails automatically
- ✅ Works with and without templates
- ✅ Configurable per tenant
- ✅ Production-ready with proper email authentication
