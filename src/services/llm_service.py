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
        self._client = None  # lazy init - don't crash on startup if AWS not configured
        self.model_id = settings.qwen_model_id

    @property
    def client(self):
        if self._client is None:
            self._client = boto3.client(
                'bedrock-runtime',
                region_name=settings.aws_region,
                aws_access_key_id=settings.aws_access_key_id,
                aws_secret_access_key=settings.aws_secret_access_key
            )
        return self._client

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
            response = await asyncio.to_thread(
                self.client.invoke_model,
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

            if 'choices' in result:
                urgency = result['choices'][0]['message'].get('content', 'medium').strip().lower()
            elif 'content' in result:
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

    async def select_template(
        self,
        message_content: str,
        tenant_id: int,
        templates: list[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Use LLM to select the most appropriate template for the message.

        Args:
            message_content: The message content to analyze
            tenant_id: Tenant ID for context
            templates: List of available templates with metadata

        Returns:
            {
                'template_id': int,
                'confidence_score': float,
                'reasoning': str
            }
        """
        if not templates:
            return {
                'template_id': None,
                'confidence_score': 0.0,
                'reasoning': 'No templates available, will use raw content'
            }

        # Build template descriptions for LLM
        template_descriptions = []
        for tmpl in templates:
            desc = f"ID: {tmpl['id']}, Name: {tmpl.get('name', 'Unnamed')}, Type: {tmpl.get('notification_type', 'general')}"
            if tmpl.get('description'):
                desc += f", Description: {tmpl['description']}"
            template_descriptions.append(desc)

        prompt = f"""You are a template selection agent. Analyze the message content and select the most appropriate template.

Message Content: {message_content[:500]}

Available Templates:
{chr(10).join(f"{i+1}. {desc}" for i, desc in enumerate(template_descriptions))}

Select the template that best matches the message content, type, and purpose.

Respond ONLY with valid JSON (no markdown, no extra text):
{{
    "template_id": <selected template ID>,
    "confidence_score": <0.0 to 1.0>,
    "reasoning": "brief explanation of why this template was selected"
}}"""

        try:
            response = await asyncio.to_thread(
                self.client.invoke_model,
                modelId=self.model_id,
                contentType='application/json',
                accept='application/json',
                body=json.dumps({
                    'messages': [{'role': 'user', 'content': prompt}],
                    'max_tokens': 300,
                    'temperature': 0.3,
                })
            )

            result = json.loads(response['body'].read())
            selection = self._parse_template_selection(result, templates)

            logger.info(f"LLM template selection: {selection['template_id']} - {selection['reasoning']}")
            return selection

        except Exception as e:
            logger.error(f"LLM template selection failed: {e}, using fallback")
            return self._fallback_template_selection(message_content, templates)

    def _parse_template_selection(self, response_body: Dict, templates: list) -> Dict[str, Any]:
        """Parse LLM template selection response."""
        try:
            content = "{}"
            if 'choices' in response_body:
                content = response_body['choices'][0]['message'].get('content', '{}')
            elif 'content' in response_body:
                content = response_body['content'][0].get('text', '{}')
            elif 'completion' in response_body:
                content = response_body['completion']

            clean_content = re.sub(r'```json\s?|\s?```', '', content).strip()
            start = clean_content.find('{')
            end = clean_content.rfind('}') + 1

            if start == -1 or end == 0:
                return self._fallback_template_selection("", templates)

            json_str = clean_content[start:end]
            selection = json.loads(json_str)

            # Validate template_id exists
            template_ids = [t['id'] for t in templates]
            if selection.get('template_id') not in template_ids:
                return self._fallback_template_selection("", templates)

            return {
                'template_id': selection.get('template_id'),
                'confidence_score': selection.get('confidence_score', 0.7),
                'reasoning': selection.get('reasoning', 'LLM selected template')
            }

        except Exception as e:
            logger.error(f"Template selection parsing error: {e}")
            return self._fallback_template_selection("", templates)

    def _fallback_template_selection(self, message_content: str, templates: list) -> Dict[str, Any]:
        """Fallback rule-based template selection."""
        if not templates:
            return {
                'template_id': None,
                'confidence_score': 0.0,
                'reasoning': 'No templates available'
            }

        # Simple fallback: select first template or match by type
        selected = templates[0]
        return {
            'template_id': selected['id'],
            'confidence_score': 0.5,
            'reasoning': 'Fallback rule-based selection (first available template)'
        }

    async def determine_channel_priority(
        self,
        message_content: str,
        urgency: str,
        user_context: Dict[str, Any],
        template_info: Dict[str, Any],
        provider_health: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Use LLM to determine optimal channel priority order.

        Args:
            message_content: The notification message content
            urgency: Urgency level (critical/high/medium/low)
            user_context: User preferences and engagement history
            template_info: Selected template information
            provider_health: Current health status of providers

        Returns:
            {
                'priority_order': ['sms', 'push', 'email', ...],
                'timing': 'immediate|scheduled',
                'scheduled_time': <timestamp or None>,
                'reasoning': 'explanation of priority order'
            }
        """
        # Critical priority override
        if urgency == 'critical':
            return {
                'priority_order': ['sms', 'push', 'voice'],
                'timing': 'immediate',
                'scheduled_time': None,
                'reasoning': 'Critical urgency requires fastest, most reliable channels (SMS, Push, Voice)'
            }

        # Check quiet hours
        is_quiet = user_context.get('is_quiet_hours', False)
        if is_quiet and urgency not in ['critical', 'high']:
            tenant_channels = user_context.get('tenant_preferred_channels', [])
            quiet_channels = tenant_channels if tenant_channels else ['email', 'inapp']
            return {
                'priority_order': quiet_channels,
                'timing': 'scheduled',
                'scheduled_time': user_context.get('optimal_send_time'),
                'reasoning': 'Tenant in quiet hours, using tenant preferred channels for non-intrusive delivery'
            }

        prompt = f"""You are a channel priority agent. Determine the optimal order of notification channels.

Message Content: {message_content[:300]}
Urgency: {urgency}

Tenant Preferred Channels (set by the company): {user_context.get('tenant_preferred_channels', [])}

User Context:
- User Preferred Channels: {user_context.get('preferred_channels', {})}
- Success Rates by Channel: {user_context.get('success_rates', {})}
- Timezone: {user_context.get('timezone', 'UTC')}
- Quiet Hours: {user_context.get('quiet_hours', {})}

Template Info:
- Type: {template_info.get('notification_type', 'general')}
- Channels: {template_info.get('supported_channels', ['email', 'sms', 'push'])}

Provider Health:
- Email: {provider_health.get('email', {}).get('is_healthy', True)}
- SMS: {provider_health.get('sms', {}).get('is_healthy', True)}
- Push: {provider_health.get('push', {}).get('is_healthy', True)}
- WhatsApp: {provider_health.get('whatsapp', {}).get('is_healthy', True)}
- Slack: {provider_health.get('slack', {}).get('is_healthy', True)}

Rules:
1. HIGHEST PRIORITY: If tenant has set preferred channels, use those first
2. If user also has preferred channels, combine with tenant preferences
3. HIGH urgency: Prioritize preferred channels if healthy
4. MEDIUM/LOW urgency: Optimize for cost and preferences
5. Only include healthy providers
6. If no preferences set, fall back to urgency-based defaults

Respond ONLY with valid JSON (no markdown, no extra text):
{{
    "priority_order": ["channel1", "channel2", "channel3"],
    "timing": "immediate|scheduled",
    "scheduled_time": null,
    "reasoning": "brief explanation of priority order"
}}"""

        try:
            response = await asyncio.to_thread(
                self.client.invoke_model,
                modelId=self.model_id,
                contentType='application/json',
                accept='application/json',
                body=json.dumps({
                    'messages': [{'role': 'user', 'content': prompt}],
                    'max_tokens': 400,
                    'temperature': 0.3,
                })
            )

            result = json.loads(response['body'].read())
            priority = self._parse_priority_response(result, urgency)

            logger.info(f"LLM priority determination: {priority['priority_order']} - {priority['reasoning']}")
            return priority

        except Exception as e:
            logger.error(f"LLM priority determination failed: {e}, using fallback")
            return self._fallback_priority(urgency, user_context, provider_health)

    def _parse_priority_response(self, response_body: Dict, urgency: str) -> Dict[str, Any]:
        """Parse LLM priority determination response."""
        try:
            content = "{}"
            if 'choices' in response_body:
                content = response_body['choices'][0]['message'].get('content', '{}')
            elif 'content' in response_body:
                content = response_body['content'][0].get('text', '{}')
            elif 'completion' in response_body:
                content = response_body['completion']

            clean_content = re.sub(r'```json\s?|\s?```', '', content).strip()
            start = clean_content.find('{')
            end = clean_content.rfind('}') + 1

            if start == -1 or end == 0:
                return self._fallback_priority(urgency, {}, {})

            json_str = clean_content[start:end]
            priority = json.loads(json_str)

            return {
                'priority_order': priority.get('priority_order', ['email', 'push']),
                'timing': priority.get('timing', 'immediate'),
                'scheduled_time': priority.get('scheduled_time'),
                'reasoning': priority.get('reasoning', 'LLM determined priority order')
            }

        except Exception as e:
            logger.error(f"Priority parsing error: {e}")
            return self._fallback_priority(urgency, {}, {})

    def _fallback_priority(
        self,
        urgency: str,
        user_context: Dict[str, Any],
        provider_health: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Fallback rule-based priority determination."""
        # Respect tenant preferred channels first, even in fallback
        tenant_channels = user_context.get('tenant_preferred_channels', [])
        if tenant_channels:
            return {
                'priority_order': tenant_channels,
                'timing': 'immediate' if urgency in ['critical', 'high'] else 'scheduled',
                'scheduled_time': None,
                'reasoning': f'Fallback using tenant preferred channels for {urgency} urgency'
            }

        priority_map = {
            'critical': ['sms', 'push', 'voice'],
            'high': ['push', 'sms', 'email'],
            'medium': ['email', 'push', 'sms'],
            'low': ['email', 'inapp']
        }

        return {
            'priority_order': priority_map.get(urgency, ['email', 'push']),
            'timing': 'immediate' if urgency in ['critical', 'high'] else 'scheduled',
            'scheduled_time': None,
            'reasoning': f'Fallback rule-based priority for {urgency} urgency'
        }
