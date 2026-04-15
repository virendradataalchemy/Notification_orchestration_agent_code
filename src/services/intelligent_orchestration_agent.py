"""Intelligent Orchestration Agent for end-to-end notification processing."""

import logging
import time
from typing import Dict, Any, Optional
from datetime import datetime

from src.services.llm_service import BedrockLLMService
from src.services.template_engine import TemplateEngine
from src.core.supabase import CANDIDATES_TABLE, CLIENT_PREFERENCES_TABLE, COMMUNICATIONS_TABLE, supabase_client

logger = logging.getLogger(__name__)


class IntelligentOrchestrationAgent:
    """
    Intelligent orchestration agent that coordinates end-to-end notification processing.
    
    Pipeline flow:
    1. Accept message input and validate
    2. LLM selects best template
    3. Fetch user context and preferences
    4. LLM determines channel priority order
    5. Render template with user data
    6. Execute notification delivery in priority order
    7. Return results with reasoning
    """

    def __init__(
        self,
        client_id: int,
        llm_service: Optional[BedrockLLMService] = None,
        template_engine: Optional[TemplateEngine] = None,
    ):
        self.client_id = client_id
        self.llm_service = llm_service or BedrockLLMService()
        self.template_engine = template_engine or TemplateEngine()

    async def orchestrate_send(
        self,
        message_content: str,
        user_id: Optional[str],
        idempotency_key: Optional[str] = None,
        custom_variables: Optional[Dict[str, Any]] = None,
        recipient_overrides: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Orchestrate end-to-end notification processing.

        Returns:
            {
                'selected_template': {...},
                'priority_order': ['sms', 'push', ...],
                'delivery_status': 'sent|failed',
                'channel_used': 'sms',
                'reasoning': {...},
                'processing_time_ms': 1234
            }
        """
        start_time = time.time()
        
        try:
            direct_recipients = self._clean_recipient_overrides(recipient_overrides)
            target_label = user_id or "direct recipients"
            logger.info(f"Starting orchestration for {target_label}, client {self.client_id}")
            validation_error = self._validate_input(message_content, user_id, direct_recipients)
            if validation_error:
                return self._error_response(validation_error, start_time)

            # Check deduplication via idempotency key in Supabase
            if idempotency_key:
                existing = await supabase_client.select(
                    COMMUNICATIONS_TABLE,
                    "id,status",
                    limit=1,
                    filters={"client_id": f"eq.{self.client_id}", "idempotency_key": f"eq.{idempotency_key}"},
                )
                if existing:
                    logger.info(f"Duplicate request detected: {idempotency_key}")
                    return self._error_response("Duplicate request", start_time)

            # Fetch templates
            templates = await self._fetch_templates()
            logger.info(f"Found {len(templates)} templates for client {self.client_id}")

            # LLM template selection
            template_selection = await self.llm_service.select_template(
                message_content, self.client_id, templates
            )
            template_selection = self._attach_template_name(template_selection, templates)
            logger.info(f"Template selected: {template_selection}")

            # Fetch user context
            user_context = await self._fetch_user_context(user_id)
            logger.info(f"User context fetched for {target_label}")

            # Analyze urgency
            urgency = await self.llm_service.analyze_content_urgency(message_content)
            logger.info(f"Content urgency: {urgency}")

            # Get template info
            template_info = self._get_template_info(template_selection, templates)

            # Real provider health check from Supabase
            provider_health = await self._fetch_provider_health()

            # LLM priority determination
            priority_decision = await self.llm_service.determine_channel_priority(
                message_content, urgency, user_context, template_info, provider_health
            )
            logger.info(f"Priority order: {priority_decision['priority_order']}")
            priority_decision['priority_order'] = self._filter_priority_for_direct_recipients(
                priority_decision['priority_order'],
                user_id,
                direct_recipients,
                user_context,
            )
            if not priority_decision['priority_order']:
                return self._error_response("No contact details match the selected client channels", start_time)

            # Render template
            rendered_content = await self._render_template(
                template_selection, templates, message_content, custom_variables
            )

            # Execute delivery pipeline
            delivery_result = await self._execute_delivery_pipeline(
                priority_decision['priority_order'],
                rendered_content,
                user_id,
                direct_recipients,
                urgency,
                template_selection.get('template_id'),
                idempotency_key,
                custom_variables or {},
            )

            processing_time = int((time.time() - start_time) * 1000)
            
            return {
                'status': 'success' if delivery_result['status'] == 'sent' else 'partial',
                'selected_template': template_selection,
                'urgency': urgency,
                'priority_order': priority_decision['priority_order'],
                'delivery_status': delivery_result['status'],
                'channel_used': delivery_result.get('channel'),
                'reasoning': {
                    'template_selection': template_selection['reasoning'],
                    'priority_determination': priority_decision['reasoning'],
                    'delivery': delivery_result.get('message', '')
                },
                'processing_time_ms': processing_time
            }

        except Exception as e:
            logger.error(f"Orchestration failed: {e}", exc_info=True)
            return self._error_response(str(e), start_time)

    def _validate_input(
        self,
        message_content: str,
        user_id: Optional[str],
        direct_recipients: Dict[str, str],
    ) -> Optional[str]:
        if not message_content:
            return "message_content is required"
        if len(message_content) > 10000:
            return "message_content exceeds 10000 characters"
        if not user_id and not direct_recipients:
            return "Provide a user_id or at least one direct contact detail"
        return None

    def _clean_recipient_overrides(self, recipient_overrides: Optional[Dict[str, Any]]) -> Dict[str, str]:
        if not recipient_overrides:
            return {}
        return {
            key: str(value).strip()
            for key, value in recipient_overrides.items()
            if value is not None and str(value).strip()
        }

    def _filter_priority_for_direct_recipients(
        self,
        priority_order: list[str],
        user_id: Optional[str],
        direct_recipients: Dict[str, str],
        user_context: Dict[str, Any],
    ) -> list[str]:
        if user_id:
            return priority_order
        recipient_channels = {
            "email": bool(direct_recipients.get("email")),
            "sms": bool(direct_recipients.get("phone")),
            "voice": bool(direct_recipients.get("phone")),
            "whatsapp": bool(direct_recipients.get("whatsapp_number")),
            "slack": bool(direct_recipients.get("slack_channel")),
        }
        client_channels = user_context.get('client_preferred_channels') or []
        available_direct_channels = [channel for channel, has_recipient in recipient_channels.items() if has_recipient]
        ordered_channels = list(dict.fromkeys([*client_channels, *priority_order, *available_direct_channels]))
        return [channel for channel in ordered_channels if recipient_channels.get(channel)]

    def _attach_template_name(self, template_selection: Dict[str, Any], templates: list[Dict[str, Any]]) -> Dict[str, Any]:
        template_id = template_selection.get('template_id')
        template = next((tmpl for tmpl in templates if tmpl.get('id') == template_id), None)
        if not template:
            return template_selection
        return {
            **template_selection,
            'template_name': template.get('subject') or template.get('name') or 'Unnamed',
        }

    async def _fetch_templates(self) -> list[Dict[str, Any]]:
        """Fetch active templates — client-specific first, fall back to all templates."""
        def _serialize(rows):
            return [
                {
                    'id': t['id'],
                    'name': t.get('name', 'Unnamed'),
                    'subject': t.get('subject'),
                    'notification_type': t.get('notification_type', 'general'),
                    'description': '',
                    'content': t.get('content', ''),
                    'supported_channels': ['email', 'sms', 'push', 'whatsapp', 'voice'],
                }
                for t in rows
            ]

        try:
            rows = await supabase_client.select(
                "templates",
                "id,name,subject,notification_type,content,channel_id",
                filters={"client_id": f"eq.{self.client_id}", "is_active": "eq.true"},
            )
            if rows:
                return _serialize(rows)

            # Client has no templates — fall back to all active templates
            logger.info(f"No templates for client {self.client_id}, using platform-wide templates")
            all_rows = await supabase_client.select(
                "templates",
                "id,name,subject,notification_type,content,channel_id",
                filters={"is_active": "eq.true"},
            )
            return _serialize(all_rows)
        except Exception as e:
            logger.error(f"Failed to fetch templates: {e}")
            return []

    async def _fetch_user_context(self, user_id: Optional[str]) -> Dict[str, Any]:
        """Fetch client preferences from the client_preferences table using client_id."""
        default = {
            'preferred_channels': {'default': ['email', 'push']},
            'client_preferred_channels': [],
            'success_rates': {},
            'timezone': 'UTC',
            'quiet_hours': {'start': '22:00', 'end': '08:00'},
            'is_quiet_hours': False,
        }

        # Fetch client-level preferences (preferred channels, quiet hours, timezone)
        try:
            rows = await supabase_client.select(
                CLIENT_PREFERENCES_TABLE,
                "preferred_channels,timezone,quiet_hours",
                limit=1,
                filters={"client_id": f"eq.{self.client_id}"},
            )
            if rows:
                prefs = rows[0]
                client_channels = prefs.get('preferred_channels') or {}
                channel_list = client_channels.get('default', [])
                default.update({
                    'preferred_channels': client_channels,
                    'client_preferred_channels': channel_list,
                    'timezone': prefs.get('timezone') or 'UTC',
                    'quiet_hours': prefs.get('quiet_hours') or {'start': '22:00', 'end': '08:00'},
                })
                logger.info(f"Client {self.client_id} preferred channels: {channel_list}")
            else:
                logger.warning(f"No preferences found for client {self.client_id}, using defaults")
        except Exception as e:
            logger.error(f"Failed to fetch client preferences: {e}")

        return default

    async def _fetch_provider_health(self) -> Dict[str, Any]:
        """Fetch real provider health from Supabase providers table."""
        try:
            providers = await supabase_client.select(
                "providers", "id,name,channel_id,is_active",
                filters={"is_active": "eq.true"}
            )
            channels = await supabase_client.select("channels", "id,name,is_active")
            ch_map = {c["id"]: c["name"] for c in channels}

            health: Dict[str, Any] = {}
            for p in providers:
                ch_name = ch_map.get(p.get("channel_id"), "unknown")
                health[ch_name] = {"is_healthy": p.get("is_active", True), "provider": p.get("name")}

            # Fill missing channels as healthy (in_app, slack may not have providers row)
            for ch in ['email', 'sms', 'push', 'whatsapp', 'slack', 'voice', 'in_app']:
                if ch not in health:
                    health[ch] = {"is_healthy": True}
            return health
        except Exception as e:
            logger.error(f"Failed to fetch provider health: {e}")
            return {ch: {'is_healthy': True} for ch in ['email', 'sms', 'push', 'whatsapp', 'slack', 'voice']}

    def _get_template_info(self, template_selection: Dict[str, Any], templates: list) -> Dict[str, Any]:
        if not template_selection.get('template_id'):
            return {'notification_type': 'general', 'supported_channels': ['email', 'sms', 'push']}
        for tmpl in templates:
            if tmpl['id'] == template_selection['template_id']:
                return {
                    'notification_type': tmpl.get('notification_type', 'general'),
                    'supported_channels': tmpl.get('supported_channels', ['email', 'sms', 'push']),
                }
        return {'notification_type': 'general', 'supported_channels': ['email', 'sms', 'push']}

    async def _render_template(
        self,
        template_selection: Dict[str, Any],
        templates: list,
        message_content: str,
        custom_variables: Optional[Dict[str, Any]],
    ) -> str:
        try:
            if not template_selection.get('template_id'):
                return message_content
            template = next((t for t in templates if t['id'] == template_selection['template_id']), None)
            if not template:
                return message_content
            variables = {'message': message_content, **(custom_variables or {})}
            rendered = self.template_engine.render(template['content'], variables)
            return rendered if not rendered.startswith('[Template Error') else message_content
        except Exception as e:
            logger.error(f"Template rendering failed: {e}, using raw content")
            return message_content

    async def _execute_delivery_pipeline(
        self,
        priority_order: list[str],
        content: str,
        user_id: Optional[str],
        direct_recipients: Dict[str, str],
        urgency: str,
        template_id: Optional[int],
        idempotency_key: Optional[str],
        custom_variables: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Execute delivery via SupabaseNotificationService in priority order."""
        if not user_id:
            return await self._execute_direct_delivery_pipeline(
                priority_order,
                content,
                direct_recipients,
                urgency,
            )

        from src.services.supabase_notification_service import SupabaseNotificationService
        svc = SupabaseNotificationService()

        # Fetch candidate details so recipient info is available for all channels
        candidate_details: Dict[str, Any] = {}
        try:
            rows = await supabase_client.select(
                CANDIDATES_TABLE,
                "id,name,email,phone,whatsapp_number",
                limit=1,
                filters={"id": f"eq.{user_id}", "client_id": f"eq.{self.client_id}"},
            )
            if rows:
                candidate_details = rows[0]
        except Exception as e:
            logger.warning(f"Could not fetch candidate details: {e}")

        for channel in priority_order:
            try:
                logger.info(f"Attempting delivery via {channel}")
                result = await svc.send_notification(
                    client_id=self.client_id,
                    payload={
                        "candidate_id": user_id,
                        # Use override email if provided (e.g. step 2: HR→IT, step 3: IT→HR)
                        "email": direct_recipients.get("email") or candidate_details.get("email"),
                        "phone": direct_recipients.get("phone") or candidate_details.get("phone"),
                        "whatsapp_number": direct_recipients.get("whatsapp_number") or candidate_details.get("whatsapp_number"),
                        "slack_channel": direct_recipients.get("slack_channel"),
                        "channels": [channel],
                        # Use explicit notification_type from custom_variables if set
                        "notification_type": (custom_variables or {}).get("notification_type") or urgency,
                        "priority": urgency,
                        "template_id": template_id,
                        "body": content,
                        "idempotency_key": f"{idempotency_key}:{channel}" if idempotency_key else None,
                    }
                )
                channel_results = result.get('channels', [])
                success = any(r.get('status') in ('sent', 'delivered') for r in channel_results)
                if success:
                    logger.info(f"Successfully delivered via {channel}")
                    return {'status': 'sent', 'channel': channel, 'message': f'Delivered via {channel}'}
                err = next((r.get('error') for r in channel_results if r.get('error')), 'unknown error')
                logger.warning(f"Channel {channel} failed: {err}")
            except Exception as e:
                logger.error(f"Delivery failed via {channel}: {e}")
                continue

        logger.error("All delivery channels failed")
        return {'status': 'failed', 'channel': None, 'message': 'All delivery channels failed'}

    async def _execute_direct_delivery_pipeline(
        self,
        priority_order: list[str],
        content: str,
        direct_recipients: Dict[str, str],
        urgency: str,
    ) -> Dict[str, Any]:
        """Deliver to explicit contact fields without resolving a Supabase candidate."""
        from src.providers import get_provider_for_channel
        from src.providers.base import Message, ProviderStatus

        recipient_by_channel = {
            "email": direct_recipients.get("email"),
            "sms": direct_recipients.get("phone"),
            "voice": direct_recipients.get("phone"),
            "whatsapp": direct_recipients.get("whatsapp_number"),
            "slack": direct_recipients.get("slack_channel"),
        }

        for channel in priority_order:
            recipient = recipient_by_channel.get(channel)
            if not recipient:
                continue

            try:
                logger.info(f"Attempting direct delivery via {channel}")
                provider = get_provider_for_channel(channel)
                if not provider:
                    logger.warning(f"Direct delivery provider not configured for {channel}")
                    continue

                response = await provider.send(
                    Message(
                        recipient=recipient,
                        subject="Notification",
                        body=content,
                        data={"body": content},
                        metadata={
                            "priority": urgency,
                            "channel": channel,
                            "client_id": self.client_id,
                            "direct_recipient": True,
                        },
                    )
                )
                if response.status == ProviderStatus.SUCCESS:
                    provider_status = response.metadata.get('status') if response.metadata else None
                    message = f'Accepted by {channel}'
                    if provider_status:
                        message = f'{message}; provider status: {provider_status}'
                    logger.info(f"Successfully accepted direct delivery via {channel}: {message}")
                    return {'status': 'sent', 'channel': channel, 'message': message}
                logger.warning(f"Direct channel {channel} failed: {response.error_message or response.status}")
            except Exception as e:
                logger.error(f"Direct delivery failed via {channel}: {e}")
                continue

        logger.error("All direct delivery channels failed")
        return {'status': 'failed', 'channel': None, 'message': 'All direct delivery channels failed'}

    def _error_response(self, error: str, start_time: float) -> Dict[str, Any]:
        """Build error response."""
        processing_time = int((time.time() - start_time) * 1000)
        return {
            'status': 'error',
            'error': error,
            'processing_time_ms': processing_time
        }
