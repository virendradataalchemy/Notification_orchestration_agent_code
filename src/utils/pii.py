import re
from typing import Any, Dict, Union

def mask_email(email: str) -> str:
    """Masks an email address (e.g. j***@example.com)."""
    if not email or "@" not in email:
        return email
    local, domain = email.split("@", 1)
    if len(local) > 1:
        local = f"{local[0]}***"
    else:
        local = "***"
    return f"{local}@{domain}"

def mask_phone(phone: str) -> str:
    """Masks a phone number (e.g. +123***7890)."""
    if not phone:
        return phone
    # Basic masking keeping first 3 and last 4
    if len(phone) > 7:
        return f"{phone[:3]}***{phone[-4:]}"
    return "***"

def mask_pii_in_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively masks known PII keys in a dictionary."""
    masked_data = {}
    
    pii_keys_email = {"email", "sender", "recipient", "from", "to", "sender_address"}
    pii_keys_phone = {"phone", "phone_number", "mobile", "whatsapp"}
    
    for key, value in data.items():
        lower_key = key.lower()
        if isinstance(value, dict):
            masked_data[key] = mask_pii_in_dict(value)
        elif isinstance(value, list):
            masked_data[key] = [
                mask_pii_in_dict(v) if isinstance(v, dict) else v 
                for v in value
            ]
        elif isinstance(value, str):
            if any(k in lower_key for k in pii_keys_email) and "@" in value:
                masked_data[key] = mask_email(value)
            elif any(k in lower_key for k in pii_keys_phone) and any(c.isdigit() for c in value):
                masked_data[key] = mask_phone(value)
            else:
                masked_data[key] = value
        else:
            masked_data[key] = value
            
    return masked_data
