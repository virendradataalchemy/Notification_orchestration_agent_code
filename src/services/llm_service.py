"""LLM service using AWS Bedrock for intelligent routing decisions."""

import asyncio
import boto3
import json
import logging
from typing import Dict, Any, Optional
from datetime import datetime
import re

from src.config import settings

logger = logging.getLogger(__name__)


class BedrockLLMService:
    """LLM service using AWS Bedrock Qwen model for routing decisions."""

    def __init__(self):
        self.client = boto3.client(
            'bedrock-runtime',
            region_name=settings.aws_region,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key
        )
        self.model_id = settings.qwen_model_id

    async def make_routing_decision(
        self,
        notification_content: str,
        user_context: Dict[str, Any],
        provider_health: Dict[str, Any],
        priority: str
    ) -> Dict[str, Any]:
        """
        Use LLM to make intelligent routing decision.

        Args:
            notification_content: The notification message content
            user_context: User preferences and engagement history
            provider_health: Current health status of providers
            priority: Notification priority level

        Returns:
            {
                'channel': 'email|sms|push|whatsapp|slack',
                'timing': 'immediate|scheduled',
                'scheduled_time': <timestamp or None>,
                'retry_strategy': 'aggressive|standard|relaxed',
                'reasoning': 'why this decision was made'
            }
        """
        prompt = self._build_routing_prompt(
            notification_content, user_context, provider_health, priority
        )

        try:
            # Run boto3 call in thread pool to avoid blocking the event loop
            response = await asyncio.to_thread(
                self.client.invoke_model,
                modelId=self.model_id,
                contentType='application/json',
                accept='application/json',
                body=json.dumps({
                    'messages': [{'role': 'user', 'content': prompt}],
                    'max_tokens': 500,
                    'temperature': 0.3,  # Lower temperature for more consistent decisions
                })
            )

            result = json.loads(response['body'].read())
            decision = self._parse_llm_response(result)

            logger.info(f"LLM routing decision: {decision['channel']} - {decision['reasoning']}")
            return decision

        except Exception as e:
            logger.error(f"LLM routing failed: {e}, falling back to rule-based routing")
            return self._fallback_routing(priority)

    def _build_routing_prompt(
        self, content: str, user_context: Dict, health: Dict, priority: str
    ) -> str:
        """Build the prompt for LLM routing decision."""
        return f"""You are a notification routing agent. Analyze the following notification and decide the best delivery channel and timing.

Notification Content: {content[:300]}...
Priority: {priority}

User Context:
- Preferred Channels: {user_context.get('preferred_channels', {})}
- Success Rates by Channel: {user_context.get('success_rates', {})}
- Current Time: {user_context.get('current_time')}
- User Timezone: {user_context.get('timezone', 'UTC')}
- Quiet Hours: {user_context.get('quiet_hours', {})}

Provider Health Status:
- Email: {health.get('email', 'healthy')}
- SMS: {health.get('sms', 'healthy')}
- Push: {health.get('push', 'healthy')}
- WhatsApp: {health.get('whatsapp', 'healthy')}
- Slack: {health.get('slack', 'healthy')}

Routing Rules:
1. CRITICAL priority: Use fastest, most reliable channel (SMS, Voice, Push)
2. HIGH priority: Use user's preferred channel if healthy, otherwise fallback
3. MEDIUM/LOW priority: Optimize for cost and user preferences
4. Respect quiet hours for non-urgent notifications
5. Choose channels with highest success rates for this user

Respond ONLY with valid JSON (no markdown, no extra text):
{{
    "channel": "email|sms|push|whatsapp|slack",
    "timing": "immediate|scheduled",
    "scheduled_time": null,
    "retry_strategy": "aggressive|standard|relaxed",
    "reasoning": "brief explanation of why this channel and timing"
}}"""

    # def _parse_llm_response(self, response: Dict) -> Dict[str, Any]:
    #     """Parse LLM JSON response."""
    #     try:
    #         # Extract content from Bedrock response
    #         if 'content' in response:
    #             content = response['content'][0].get('text', '{}')
    #         elif 'completion' in response:
    #             content = response['completion']
    #         else:
    #             content = str(response)

    #         # Find JSON in response
    #         start = content.find('{')
    #         end = content.rfind('}') + 1

    #         if start == -1 or end == 0:
    #             raise ValueError("No JSON found in response")

    #         json_str = content[start:end]
    #         decision = json.loads(json_str)

    #         # Validate required fields
    #         required_fields = ['channel', 'timing', 'retry_strategy', 'reasoning']
    #         if not all(field in decision for field in required_fields):
    #             raise ValueError(f"Missing required fields in LLM response: {decision}")

    #         return decision

    #     except Exception as e:
    #         logger.error(f"Failed to parse LLM response: {e}, using fallback")
    #         return self._fallback_routing('medium')
        
    

    # ... inside BedrockLLMService class ...
        
    def _parse_llm_response(self, response_body: Dict) -> Dict[str, Any]:
        """Parse LLM JSON response with robust cleaning."""
        try:
            content = "{}"
            # 1. Extract content based on the 'choices' format seen in your logs
            if 'choices' in response_body:
                content = response_body['choices'][0]['message'].get('content', '{}')
            elif 'content' in response_body:
                content = response_body['content'][0].get('text', '{}')
            elif 'completion' in response_body:
                content = response_body['completion']
            
            # 2. Clean the string (handle markdown and extra text)
            clean_content = re.sub(r'```json\s?|\s?```', '', content).strip()
            
            # 3. Isolate the JSON block
            start = clean_content.find('{')
            end = clean_content.rfind('}') + 1
            
            if start == -1 or end == 0:
                return self._fallback_routing('medium')

            json_str = clean_content[start:end]
            decision = json.loads(json_str)

            # 4. Final safety check on keys
            for key in ['channel', 'timing', 'retry_strategy']:
                if key not in decision:
                    # Fill missing keys with defaults instead of crashing
                    decision[key] = self._fallback_routing('medium')[key]

            return decision

        except Exception as e:
            logger.error(f"LLM Parsing Error: {str(e)} | Raw: {str(response_body)[:200]}")
            return self._fallback_routing('medium')
            

    def _fallback_routing(self, priority: str) -> Dict[str, Any]:
        """Fallback to rule-based routing if LLM fails."""
        channel_map = {
            'critical': 'sms',
            'high': 'push',
            'medium': 'email',
            'low': 'email'
        }

        retry_map = {
            'critical': 'aggressive',
            'high': 'standard',
            'medium': 'standard',
            'low': 'relaxed'
        }

        return {
            'channel': channel_map.get(priority, 'email'),
            'timing': 'immediate' if priority in ['critical', 'high'] else 'scheduled',
            'scheduled_time': None,
            'retry_strategy': retry_map.get(priority, 'standard'),
            'reasoning': f'Fallback rule-based routing for {priority} priority'
        }

    async def classify_inbound_intent(self, parsed_content: str) -> Dict[str, Any]:
        """
        Layer 2: Fallback LLM Classification for inbound intents.
        Used when deterministic rules fail to confidently identify an intent.
        
        Returns:
            {
                'intent': 'accept|reject|request|query',
                'confidence': float,
                'rationale': str
            }
        """
        prompt = f"""You are a smart assistant classifying a reply from a candidate.

Message Content:
"{parsed_content[:800]}"

Classify the intent of this message into EXACTLY ONE of the following categories:
- accept: The candidate is agreeing, confirming, or saying yes.
- reject: The candidate is declining, saying no, or asking to stop.
- request: The candidate is asking for an action (e.g., reschedule, send info, update details).
- query: The candidate is asking a question or seeking clarification.

Respond ONLY with valid JSON in this exact format (no markdown tags):
{{
    "intent": "accept|reject|request|query|unknown",
    "confidence": 0.0 to 1.0,
    "rationale": "Brief 1-sentence explanation of why"
}}"""

        try:
            # Bedrock Primary
            response = await asyncio.to_thread(
                self.client.invoke_model,
                modelId=self.model_id,
                contentType='application/json',
                accept='application/json',
                body=json.dumps({
                    'messages': [{'role': 'user', 'content': prompt}],
                    'max_tokens': 150,
                    'temperature': 0.1,  # low temp for classification
                })
            )

            result = json.loads(response['body'].read())
            
            # Extract content from Qwen format
            content = "{}"
            if 'choices' in result:
                content = result['choices'][0]['message'].get('content', '{}')
            elif 'content' in result:
                content = result['content'][0].get('text', '{}')
            elif 'completion' in result:
                content = result['completion']
                
            clean_content = re.sub(r'```json\s?|\s?```', '', content).strip()
            
            start = clean_content.find('{')
            end = clean_content.rfind('}') + 1
            if start == -1 or end == 0:
                raise ValueError("No JSON found")

            decision = json.loads(clean_content[start:end])
            
            intent = decision.get("intent", "unknown").lower()
            if intent not in ["accept", "reject", "request", "query"]:
                intent = "unknown"
                
            return {
                "intent": intent,
                "confidence": float(decision.get("confidence", 0.5)),
                "rationale": decision.get("rationale", "LLM parsed response")
            }

        except Exception as e:
            logger.error(f"LLM Intent Classification failed: {e}")
            return {
                "intent": "unknown",
                "confidence": 0.0,
                "rationale": f"LLM Error: {str(e)}"
            }

    async def analyze_content_urgency(self, content: str) -> str:
        """
        Analyze notification content to determine urgency level.

        Returns: 'critical', 'high', 'medium', or 'low'
        """
        prompt = f"""Analyze this notification and determine its urgency level.

Content: {content[:500]}

Classify as one of: critical, high, medium, low

Critical: System outages, security alerts, emergency situations
High: Time-sensitive actions, important updates
Medium: Regular notifications, reminders
Low: Marketing, promotional content

Respond with ONLY the urgency level (one word)."""

        try:
            response = self.client.invoke_model(
                modelId=self.model_id,
                contentType='application/json',
                accept='application/json',
                body=json.dumps({
                    'messages': [{'role': 'user', 'content': prompt}],
                    'max_tokens': 10,
                    'temperature': 0.1,
                })
            )

            result = json.loads(response['body'].read())

            if 'content' in result:
                urgency = result['content'][0].get('text', 'medium').strip().lower()
            elif 'completion' in result:
                urgency = result['completion'].strip().lower()
            else:
                urgency = 'medium'

            # Validate urgency
            valid_levels = ['critical', 'high', 'medium', 'low']
            return urgency if urgency in valid_levels else 'medium'

        except Exception as e:
            logger.error(f"Failed to analyze urgency: {e}")
            return 'medium'

    async def generate_template(self, content: str, channel: str) -> Dict[str, Any]:
        """
        Generate a professional notification template based on raw content and target channel.
        """
        prompt = f"""You are a professional communications expert. Generate a notification template based on the content below for the channel: {channel}.

Raw Content/Instruction:
"{content}"

Channel Guidelines:
- email: Provide a compelling subject line and an HTML-formatted body.
- sms/whatsapp: Keep it concise (under 160 chars for SMS if possible). Use plaintext.
- slack: Use markdown formatting.
- push/inapp: Keep it short and actionable.

Use Jinja2 variable placeholders like {{{{user_name}}}}, {{{{order_id}}}}, {{{{company_name}}}} where they make sense.

Respond ONLY with valid JSON in this exact structure:
{{
    "name": "lowercase_with_underscores_name",
    "subject": "Subject line (null if not email)",
    "body": "The generated template body content",
    "description": "Short description of the template"
}}"""

        try:
            # Bedrock Primary
            response = await asyncio.to_thread(
                self.client.invoke_model,
                modelId=self.model_id,
                contentType='application/json',
                accept='application/json',
                body=json.dumps({
                    'messages': [{'role': 'user', 'content': prompt}],
                    'max_tokens': 1000,
                    'temperature': 0.7,
                })
            )

            result = json.loads(response['body'].read())
            
            # Extract content from Qwen format
            content_str = "{}"
            if 'choices' in result:
                content_str = result['choices'][0]['message'].get('content', '{}')
            elif 'content' in result:
                content_str = result['content'][0].get('text', '{}')
            elif 'completion' in result:
                content_str = result['completion']
            
            clean_content = re.sub(r'```json\s?|\s?```', '', content_str).strip()
            
            start = clean_content.find('{')
            end = clean_content.rfind('}') + 1
            if start == -1 or end == 0:
                raise ValueError("No JSON found in LLM response")

            generated = json.loads(clean_content[start:end])
            
            return {
                "name": generated.get("name"),
                "subject": generated.get("subject"),
                "body": generated.get("body", content),
                "description": generated.get("description", f"AI generated {channel} template")
            }

        except Exception as e:
            logger.error(f"AI Template Generation failed: {e}")
            return {
                "subject": "Notification" if channel == 'email' else None,
                "body": content,
                "description": "Original content (AI generation failed)"
            }

    async def generate_multi_channel_templates(self, content: str, channels: list[str]) -> Dict[str, Any]:
        """
        Generate professional notification templates for multiple channels at once using AI.
        """
        # Fallback to individual generation as multi-channel prompt is less reliable on Bedrock
        results = {"templates": {}}
        for channel in channels:
            results["templates"][channel] = await self.generate_template(content, channel)
        return results
