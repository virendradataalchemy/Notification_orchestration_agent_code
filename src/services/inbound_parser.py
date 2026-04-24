import re
from typing import Optional
from src.models.inbound import InboundMessage, InboundChannel

class InboundParserService:
    """
    Cleans raw inbound webhooks.
    Extracts plaintext, removes email thread history, signatures, etc.
    """

    def parse(self, inbound_message: InboundMessage) -> Optional[str]:
        if inbound_message.channel == InboundChannel.EMAIL:
            return self._parse_email(inbound_message.raw_payload)
        elif inbound_message.channel in [InboundChannel.SMS, InboundChannel.WHATSAPP]:
            return self._parse_sms(inbound_message.raw_payload)
        return ""

    def _parse_sms(self, raw_payload: dict) -> str:
        """
        Twilio SMS/WhatsApp payload parsing
        """
        body = raw_payload.get("Body", "")
        # For SMS, usually little cleaning is needed, but we can strip trailing whitespace
        return body.strip()

    def _parse_email(self, raw_payload: dict) -> str:
        """
        Mailgun inbound payload parsing.
        Removes quoted text and common signatures.
        """
        # Mailgun usually sends 'stripped-text' which already removes signatures/quotes!
        # If available, we trust Mailgun's parsing algorithm.
        stripped_text = raw_payload.get("stripped-text", "")
        if stripped_text:
            return stripped_text.strip()

        # Fallback if stripped-text isn't provided, use 'body-plain' and clean manually
        body = raw_payload.get("body-plain", "")
        if not body:
            return ""

        return self._clean_email_body(body)

    def _clean_email_body(self, text: str) -> str:
        """
        A basic regex fallback cleaner for emails without stripped-text.
        """
        # Remove lines starting with > (quoted replies)
        lines = text.split('\n')
        cleaned_lines = []
        for line in lines:
            if line.startswith(">") or line.startswith("On ") and "wrote:" in line:
                # Basic heuristic to stop parsing at thread history
                break
            # common signature markers
            if line.strip() in ["--", "-- ", "___", "Best,", "Regards,", "Sincerely,"]:
                break
            cleaned_lines.append(line)
        
        return "\n".join(cleaned_lines).strip()
