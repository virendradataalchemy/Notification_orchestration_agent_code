import re
import logging
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.inbound import InboundMessage, InboundIntent, IntentCategory, DetectionMethod
from src.services.llm_service import BedrockLLMService

logger = logging.getLogger(__name__)

class IntentEngineService:
    """
    Hybrid 2-layer intent detection engine.
    Layer 1: Deterministic rules (Regex)
    Layer 2: LLM Fallback
    """

    def __init__(self, db_session: AsyncSession):
        self.db = db_session
        self.llm_service = BedrockLLMService()

        # Simple deterministic rules (Ordered by priority)
        self.rules = {
            IntentCategory.REJECT: [
                r"\b(no|reject|decline|not interested|stop|cancel|unsubscribe|don't|dont|not want)\b",
                r"\b(not|never|won't|wont)\s+(accept|agree|interested|confirm|sure|good)\b"
            ],
            IntentCategory.ACCEPT: [
                r"\b(yes|confirm|accept|agree|interested|sure|sounds good|ok|okay|yep|yup|yeah)\b"
            ],
            IntentCategory.REQUEST: [
                r"\b(reschedule|update|change time|send more info|call me|provide details)\b"
            ],
            IntentCategory.QUERY: [
                r"\b(what|how|where|when|who|why|can you clarify|meaning)\b",
                r"\?$" # Ends with question mark
            ]
        }

    async def detect_intent(self, inbound_message: InboundMessage) -> InboundIntent:
        text = (inbound_message.parsed_content or "").lower().strip()
        
        # Layer 1: Rules
        detected_intent = None
        matched_rule = None

        if text:
            for category, patterns in self.rules.items():
                for pattern in patterns:
                    if re.search(pattern, text):
                        detected_intent = category
                        matched_rule = pattern
                        break
                if detected_intent:
                    break

        if detected_intent:
            intent_record = InboundIntent(
                message_id=inbound_message.id,
                intent=detected_intent,
                confidence=1.0, # Deterministic is 100% confident
                detection_method=DetectionMethod.RULES,
                rationale=f"Matched Regex Pattern: {matched_rule}"
            )
            self.db.add(intent_record)
            logger.info(f"Rules engine matched {detected_intent} for message {inbound_message.id}")
            return intent_record

        # Layer 2: LLM Fallback
        logger.info(f"Rules failed, falling back to LLM for message {inbound_message.id}")
        
        fallback_text = text
        if not fallback_text:
            raw = inbound_message.raw_payload or {}
            # Keep LLM input always as text; avoid passing dict payloads.
            fallback_text = (
                raw.get("stripped-text")
                or raw.get("body-plain")
                or raw.get("Body")
                or raw.get("subject")
                or ""
            )

        llm_decision = await self.llm_service.classify_inbound_intent(fallback_text)
        
        # Map string to Enum
        try:
            mapped_intent = IntentCategory(llm_decision["intent"])
        except ValueError:
            mapped_intent = IntentCategory.UNKNOWN

        intent_record = InboundIntent(
            message_id=inbound_message.id,
            intent=mapped_intent,
            confidence=llm_decision["confidence"],
            detection_method=DetectionMethod.LLM,
            rationale=llm_decision["rationale"]
        )
        self.db.add(intent_record)
        return intent_record
