# Changelog

## [2026-05-12] - Email Branding Feature

### Added
- Automatic branding footer for all emails (with or without templates)
- Company logo display in email footers
- Contact information display (phone, email, website)
- `tenant_branding` database table for storing branding configuration
- API endpoints for managing branding (`/api/v1/branding`)
- `render_raw_content()` method for applying branding to non-template emails

### Changed
- `notification_service.py`: Updated to apply branding to all email types
  - Single notifications now include branding footer
  - Batch notifications now include branding footer
  - Batch multichannel notifications now include branding footer
- `tenant_template_engine.py`: Enhanced to support branding for raw content

### Fixed
- Logo not appearing in emails sent without templates
- Branding footer not being applied to batch notifications
- Base64 images being blocked by Gmail (switched to external URLs)

### Technical Details
- Modified 3 locations in `notification_service.py` to call `render_raw_content()`
- Branding footer automatically appends to email body before sending
- Supports both custom HTML footers and default template
- Logo URL can be external URL or base64 data URI (external recommended)

### Files Modified
- `src/services/notification_service.py`
- `src/services/tenant_template_engine.py`
- `src/models/tenant_branding.py`
- `src/api/routers/branding.py`

### Migration
- `migrations/versions/2026_05_12_2205-add_tenant_branding.py`

### Utilities
- `debug_branding.py` - Check branding configuration
- `setup_branding.py` - Initial branding setup script

### Documentation
- `BRANDING_FEATURE.md` - Complete feature documentation
