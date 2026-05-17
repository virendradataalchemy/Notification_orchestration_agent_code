import re
import logging
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.inbound import InboundMessageParsed, InboundMessageRaw, InboundIntent, IntentCategory, DetectionMethod
from src.services.llm_service import BedrockLLMService

logger = logging.getLogger(__name__)

QUESTION_WORD_PATTERN = re.compile(
    r"\b(what|how|where|when|who|why|which|do you|can you|could you|would you|is there|are there|can i|could i)\b"
)
QUESTION_MARK_PATTERN = re.compile(r"\?")
HARD_REJECT_PATTERN = re.compile(
    r"\b(stop|unsubscribe|remove me|do not contact|don't contact|dont contact|opt out)\b"
)
NEGATIVE_FEEDBACK_PATTERN = re.compile(
    r"\b(don't like|dont like|not like|didn't like|didnt like|dislike|not a fit|not suitable)\b"
)
ALTERNATIVE_QUERY_PATTERN = re.compile(
    r"\b(do you have|any other|other options|other flavours|other flavors|alternatives?|something else)\b"
)
REQUEST_PATTERN = re.compile(
    r"\b(reschedule|update|change time|send more info|call me|provide details)\b"
)

class IntentEngineService:
    """
    Hybrid 2-layer intent detection engine.
    Layer 1: Deterministic rules (Regex)
    Layer 2: LLM Fallback
    """

    def __init__(self, db_session: AsyncSession):
        self.db = db_session
        self.llm_service = BedrockLLMService()

        # Deterministic rules. We score all category matches first and then
        # resolve mixed-intent replies with extra logic instead of stopping at
        # the first regex hit.
        self.rules = {
            IntentCategory.QUERY: [
                r"\b(what|how|where|when|who|why|which|do you|can you clarify|meaning|do you have|any other|other options|other flavours|other flavors|alternatives?)\b",
                r"\?$" # Ends with question mark
            ],
            IntentCategory.REQUEST: [
                r"\b(reschedule|update|change time|send more info|call me|provide details)\b"
            ],
            IntentCategory.REJECT: [
                r"\b(no|reject|decline|not interested|stop|cancel|unsubscribe|don't|dont|not want)\b",
                r"\b(not|never|won't|wont)\s+(accept|agree|interested|confirm|sure|good|like|want)\b"
            ],
            IntentCategory.ACCEPT: [
                r"\b(yes|confirm|accept|agree|interested|sure|sounds good|ok|okay|yep|yup|yeah)\b"
            ]
        }

    async def detect_intent(self, parsed_msg: InboundMessageParsed, raw_msg: InboundMessageRaw) -> InboundIntent:
        text = (parsed_msg.parsed_content or "").lower().strip()
        
        # Layer 1: Rules
        detected_intent = None
        rationale = None
        confidence = 1.0
        needs_review = False

        if text:
            detected_intent, rationale, confidence, needs_review = self._detect_by_rules(text)

        if detected_intent:
            intent_record = InboundIntent(
                parsed_message_id=parsed_msg.id,
                intent=detected_intent,
                confidence=confidence,
                detection_method=DetectionMethod.RULES,
                rationale=rationale,
                needs_review=needs_review
            )
            self.db.add(intent_record)
            logger.info(f"Rules engine matched {detected_intent} for message {parsed_msg.id}")
            return intent_record

        # Layer 2: LLM Fallback
        logger.info(f"Rules failed, falling back to LLM for message {parsed_msg.id}")
        
        fallback_text = text
        if not fallback_text:
            raw = raw_msg.raw_payload or {}
            # Keep LLM input always as text; avoid passing dict payloads.
            fallback_text = (
                raw.get("stripped-text")
                or raw.get("body-plain")
                or raw.get("Body")
                or raw.get("subject")
                or ""
            )

        # Let's ensure text isn't a dict. If it is, cast it to string safely.
        if isinstance(fallback_text, dict):
            fallback_text = str(fallback_text)

        # Await the LLM classification natively, without run_until_complete
        llm_decision = await self.llm_service.classify_inbound_intent(fallback_text)
        
        # Map string to Enum
        try:
            mapped_intent = IntentCategory(llm_decision["intent"])
        except ValueError:
            mapped_intent = IntentCategory.UNKNOWN

        confidence = llm_decision.get("confidence", 0.0)
        needs_review = confidence < 0.70 or mapped_intent == IntentCategory.UNKNOWN

        intent_record = InboundIntent(
            parsed_message_id=parsed_msg.id,
            intent=mapped_intent,
            confidence=confidence,
            detection_method=DetectionMethod.LLM,
            rationale=llm_decision.get("rationale"),
            needs_review=needs_review
        )
        self.db.add(intent_record)
        return intent_record

    def _detect_by_rules(
        self,
        text: str,
    ) -> tuple[IntentCategory | None, str | None, float, bool]:
        matched_by_category: dict[IntentCategory, list[str]] = {}
        for category, patterns in self.rules.items():
            hits = [pattern for pattern in patterns if re.search(pattern, text)]
            if hits:
                matched_by_category[category] = hits

        if not matched_by_category:
            return None, None, 0.0, False

        has_question_signal = bool(
            QUESTION_MARK_PATTERN.search(text) or QUESTION_WORD_PATTERN.search(text)
        )
        has_hard_reject = bool(HARD_REJECT_PATTERN.search(text))
        has_negative_feedback = bool(NEGATIVE_FEEDBACK_PATTERN.search(text))
        asks_for_alternative = bool(ALTERNATIVE_QUERY_PATTERN.search(text))
        has_request_signal = bool(REQUEST_PATTERN.search(text))

        # Hard opt-out language wins unless the message is clearly a request.
        if has_hard_reject and not has_request_signal:
            return (
                IntentCategory.REJECT,
                "Matched hard opt-out language",
                1.0,
                False,
            )

        # Action-oriented messages should stay as REQUEST even if phrased as a question.
        if has_request_signal:
            return (
                IntentCategory.REQUEST,
                "Matched request/action language",
                0.98 if has_question_signal else 1.0,
                False,
            )

        # Negative feedback plus a follow-up question is engagement, not a pure reject.
        if has_question_signal and (has_negative_feedback or asks_for_alternative):
            return (
                IntentCategory.QUERY,
                "Question-seeking reply with negative feedback prioritized as query",
                0.96,
                False,
            )

        # General question signals beat soft negative wording.
        if has_question_signal and IntentCategory.QUERY in matched_by_category:
            return (
                IntentCategory.QUERY,
                f"Matched query patterns: {matched_by_category[IntentCategory.QUERY]}",
                0.95 if IntentCategory.REJECT in matched_by_category else 1.0,
                False,
            )

        # Fall back to a stable priority order for the remaining deterministic cases.
        fallback_order = (
            IntentCategory.REJECT,
            IntentCategory.ACCEPT,
            IntentCategory.REQUEST,
            IntentCategory.QUERY,
        )
        for category in fallback_order:
            if category in matched_by_category:
                return (
                    category,
                    f"Matched {category.value} patterns: {matched_by_category[category]}",
                    1.0,
                    False,
                )

        return None, None, 0.0, False
