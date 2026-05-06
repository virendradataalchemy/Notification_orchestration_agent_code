from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Dict, Any
import uuid
import logging
import hashlib
import json
from datetime import datetime, timedelta
from fastapi import HTTPException, status as http_status

logger = logging.getLogger(__name__)

from src.models import (
    Notification,
    NotificationChannel,
    NotificationStatus,
    Priority as DBPriority,
    ChannelStatus,
    TenantChannelPreference,
    Tenant,
    TenantProviderConfig,
)
from src.api.schemas import (
    SendNotificationRequest,
    BatchNotificationRequest,
    BatchMultiChannelNotificationRequest,
    NotificationResponse,
    BatchNotificationResponse,
    BatchMultiChannelNotificationResponse,
    Priority,
)
from .router import MessageRouter
from .template_engine import TemplateEngine
from .tenant_template_engine import TenantTemplateEngine
from .usage_tracker import usage_tracker
from .orchestration_agent import OrchestrationAgent
from .channel_policy import channels_requiring_templates, get_provider_for_channel


class NotificationService:
    """Service for managing notifications."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.router = MessageRouter(db)
        self.template_engine = TemplateEngine()
        self.tenant_template_engine = TenantTemplateEngine()

    async def _find_recent_duplicate_notification_id(
        self,
        tenant_id: str,
        user_id: str,
        notification_type: str,
        body: str | None,
        window_minutes: int = 10,
    ) -> str | None:
        """
        Resolve a duplicate to an existing notification id when cache-only dedup
        does not return a concrete id.
        """
        if not body:
            return None

        window_start = datetime.utcnow() - timedelta(minutes=window_minutes)
        result = await self.db.execute(
            select(Notification).where(
                Notification.tenant_id == tenant_id,
                Notification.user_id == user_id,
                Notification.type == notification_type,
                Notification.created_at >= window_start,
            ).order_by(Notification.created_at.desc())
        )
        candidates = result.scalars().all()
        for candidate in candidates:
            candidate_body = (candidate.data or {}).get("body")
            if candidate_body == body:
                return str(candidate.id)
        return None

    def _build_request_fingerprint(
        self,
        tenant_id: str,
        request: SendNotificationRequest,
    ) -> str:
        """Build deterministic fingerprint for duplicate-submit protection."""
        payload = {
            "tenant_id": tenant_id,
            "user_id": request.recipient.user_id,
            "email": request.recipient.email,
            "phone": request.recipient.phone,
            "type": request.notification.type,
            "priority": request.notification.priority.value,
            "subject": request.notification.subject,
            "body": request.notification.body,
            "template_id": request.notification.template_id,
            "channels": [c.value for c in request.notification.channels],
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _build_batch_request_fingerprint(
        self,
        tenant_id: str,
        request: BatchNotificationRequest | BatchMultiChannelNotificationRequest,
    ) -> str:
        """Build deterministic fingerprint for batch duplicate-submit protection."""
        # Create a stable representation of the recipients
        recipients_data = []
        for r in request.recipients:
            recipients_data.append({
                "user_id": r.user_id,
                "email": r.email,
                "phone": r.phone,
            })
        
        # Sort to ensure order doesn't change the fingerprint if same recipients
        recipients_data.sort(key=lambda x: str(x.get("user_id", "")))
        
        payload = {
            "tenant_id": tenant_id,
            "recipients_hash": hashlib.sha256(json.dumps(recipients_data, sort_keys=True).encode()).hexdigest(),
            "subject": request.subject,
            "body": request.body,
            "template_id": request.template_id,
            "data": request.data if hasattr(request, "data") else None,
        }
        
        if hasattr(request, "channel"):
            payload["channels"] = [request.channel.value]
        elif hasattr(request, "channels"):
            payload["channels"] = [c.value for c in request.channels]
            
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        fp = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        import logging
        logging.getLogger(__name__).info(f"Generated batch fingerprint for {tenant_id}: {fp} with payload: {canonical}")
        return fp

    async def _find_recent_duplicate_by_fingerprint(
        self,
        tenant_id: str,
        fingerprint: str,
        window_minutes: int = 10,
    ) -> str | None:
        """Find recent notification already created with same fingerprint."""
        # Check in Redis cache first for faster batch dedup
        try:
            from src.core import get_redis_client
            redis = await get_redis_client()
            key = f"fingerprint:{tenant_id}:{fingerprint}"
            existing = await redis.get(key)
            if existing:
                return existing.decode() if hasattr(existing, 'decode') else str(existing)
        except Exception as e:
            logger.warning(f"Error checking request fingerprint in Redis: {e}")

        # Fallback to DB check
        window_start = datetime.utcnow() - timedelta(minutes=window_minutes)
        result = await self.db.execute(
            select(Notification).where(
                Notification.tenant_id == tenant_id,
                Notification.created_at >= window_start,
            ).order_by(Notification.created_at.desc())
        )
        for candidate in result.scalars().all():
            candidate_fingerprint = (candidate.data or {}).get("request_fingerprint")
            if candidate_fingerprint == fingerprint:
                # If we found it in DB but not Redis, store it in Redis for next time
                try:
                    from src.core import get_redis_client
                    redis = await get_redis_client()
                    key = f"fingerprint:{tenant_id}:{fingerprint}"
                    await redis.setex(key, window_minutes * 60, str(candidate.id))
                except Exception:
                    pass
                return str(candidate.id)
        return None

    async def send_notification(
        self, tenant_id: str, request: SendNotificationRequest, owner_id: str | None = None
    ) -> NotificationResponse:
        """
        Send a notification to a single recipient.

        Args:
            tenant_id: Tenant identifier
            request: Notification request data

        Returns:
            NotificationResponse with notification ID and status

        Raises:
            HTTPException: If tenant quota is exceeded
        """
        # Check tenant quota
        from fastapi import HTTPException, status as http_status
        from sqlalchemy import select

        allowed, usage_info = await usage_tracker.check_quota(self.db, tenant_id)
        if not allowed:
            raise HTTPException(
                status_code=http_status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Monthly quota exceeded. Used: {usage_info['used']}/{usage_info['quota']}. "
                       f"Resets on: {usage_info['reset_date']}"
            )

        # Enforce hard template requirements before dedup/orchestration shortcuts.
        requested_channels = [c.value for c in request.notification.channels]
        required_template_channels = set(channels_requiring_templates())
        missing_required_template_channels = [
            ch for ch in requested_channels if ch in required_template_channels
        ]
        if missing_required_template_channels and not request.notification.template_id:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"template_id is required for channels: {missing_required_template_channels}. "
                    "Create a tenant template first and pass template_id."
                )
            )

        # === Idempotency Check ===
        idempotency_key = getattr(request.notification, 'idempotency_key', None)
        if idempotency_key:
            # Check Redis cache first (faster)
            try:
                from src.core import get_redis_client
                from src.utils.deduplication import DeduplicationService

                redis = await get_redis_client()
                dedup = DeduplicationService(redis)
                existing_id = await dedup.check_idempotency_key(idempotency_key)

                if existing_id:
                    logger.info(f"Duplicate detected in Redis cache: {idempotency_key}")
                    return NotificationResponse(
                        notification_id=existing_id,
                        status=NotificationStatus.QUEUED,
                        channels={},
                        estimated_delivery=datetime.utcnow(),
                        created_at=datetime.utcnow(),
                    )
            except Exception as e:
                logger.warning(f"Redis idempotency check failed: {e}")

            # Check database as fallback
            try:
                existing_notif = await self.db.execute(
                    select(Notification).where(
                        Notification.tenant_id == tenant_id,
                        Notification.idempotency_key == idempotency_key
                    )
                )
                existing = existing_notif.scalar_one_or_none()

                if existing:
                    logger.info(f"Duplicate detected in database: {idempotency_key}")
                    # Return the existing notification
                    return NotificationResponse(
                        notification_id=str(existing.id),
                        status=NotificationStatus.QUEUED,  # Return original status
                        channels={},
                        estimated_delivery=datetime.utcnow(),
                        created_at=existing.created_at,
                    )
            except Exception as e:
                logger.error(f"Database idempotency check failed: {e}")
                await self.db.rollback()
                # Continue processing without idempotency check
        else:
            # Safety net for clients that do not pass idempotency_key.
            request_fingerprint = self._build_request_fingerprint(tenant_id, request)
            existing_recent_id = await self._find_recent_duplicate_by_fingerprint(
                tenant_id=tenant_id,
                fingerprint=request_fingerprint,
            )
            if existing_recent_id:
                logger.info(
                    "Duplicate detected via request fingerprint for tenant=%s user=%s",
                    tenant_id,
                    request.recipient.user_id,
                )
                return NotificationResponse(
                    notification_id=existing_recent_id,
                    status=NotificationStatus.QUEUED,
                    channels={},
                    estimated_delivery=datetime.utcnow(),
                    created_at=datetime.utcnow(),
                )

        # === NEW: Orchestration Agent Processing ===
        llm_decision = None
        try:
            logger.info(f"Running orchestration agent for user {request.recipient.user_id}")

            agent = OrchestrationAgent(self.db)

            orchestration_result = await agent.process_notification(
                tenant_id=tenant_id,
                user_id=request.recipient.user_id,
                notification_type=request.notification.type,
                content=request.notification.body,
                priority=request.notification.priority.value,
                requested_channels=[c.value for c in request.notification.channels],
                metadata={
                    'idempotency_key': idempotency_key,
                    'tenant_id': tenant_id
                }
            )

            # Handle duplicates
            if orchestration_result['status'] == 'duplicate':
                logger.info(
                    f"Duplicate notification detected: {orchestration_result['reason']}"
                )
                existing_id = orchestration_result.get('notification_id')
                if not existing_id:
                    existing_id = await self._find_recent_duplicate_notification_id(
                        tenant_id=tenant_id,
                        user_id=request.recipient.user_id,
                        notification_type=request.notification.type,
                        body=request.notification.body,
                    )
                if not existing_id:
                    raise HTTPException(
                        status_code=http_status.HTTP_409_CONFLICT,
                        detail=(
                            "Duplicate notification detected but existing record could not be resolved. "
                            "Provide idempotency_key to guarantee deterministic deduplication."
                        ),
                    )
                return NotificationResponse(
                    notification_id=existing_id,
                    status=NotificationStatus.QUEUED,
                    channels={},
                    estimated_delivery=datetime.utcnow(),
                    created_at=datetime.utcnow(),
                )

            # Store LLM decision for analytics
            llm_decision = orchestration_result.get('llm_decision')

            logger.info(
                f"Orchestration complete: channel={llm_decision.get('channel')}, "
                f"reasoning={llm_decision.get('reasoning')}"
            )

        except Exception as e:
            logger.error(f"Orchestration agent failed, using fallback: {e}")
            llm_decision = None

        # Map priority
        priority_map = {
            Priority.CRITICAL: DBPriority.CRITICAL,
            Priority.HIGH: DBPriority.HIGH,
            Priority.MEDIUM: DBPriority.MEDIUM,
            Priority.LOW: DBPriority.LOW,
        }

        delivery_mode = getattr(request.notification, "delivery_mode", None)
        strict_client_priority = getattr(request.notification, "strict_client_priority", True)
        ai_fallback_enabled = getattr(request.notification, "ai_fallback_enabled", True)
        ai_on_no_channel_preference = getattr(request.notification, "ai_on_no_channel_preference", True)

        tenant_row = await self.db.get(Tenant, tenant_id)
        tenant_config = (tenant_row.config or {}) if tenant_row else {}
        tenant_default_channel_priority = tenant_config.get("default_channel_priority") or []
        tenant_default_delivery_mode = tenant_config.get("default_delivery_mode") or "parallel_all"
        if tenant_default_delivery_mode not in {"parallel_all", "sequential_failover"}:
            tenant_default_delivery_mode = "parallel_all"
        delivery_mode_value = delivery_mode.value if delivery_mode else tenant_default_delivery_mode

        resolved_email = request.recipient.email
        resolved_phone = request.recipient.phone
        resolved_slack_id = request.recipient.slack_id
        resolved_device_tokens = request.recipient.device_tokens

        client_requested_channels = [c.value for c in request.notification.channels]
        channel_preference_source = "request"
        if not client_requested_channels and tenant_default_channel_priority:
            client_requested_channels = tenant_default_channel_priority
            channel_preference_source = "tenant_default"

        has_client_channel_preference = len(client_requested_channels) > 0

        # Enforce tenant-level channel preferences.
        # If tenant has no explicit preferences, default is all channels enabled.
        prefs_result = await self.db.execute(
            select(TenantChannelPreference).where(TenantChannelPreference.tenant_id == tenant_id)
        )
        prefs = prefs_result.scalars().all()
        enabled_map = {p.channel: p.enabled for p in prefs} if prefs else {}

        def _is_enabled(channel: str) -> bool:
            return enabled_map.get(channel, True) if enabled_map else True

        supported_channels = ["email", "sms", "whatsapp", "slack", "voice"] # "push", "inapp"]
        available_channels = [ch for ch in supported_channels if _is_enabled(ch)]

        if not available_channels:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="No delivery channels are enabled for this tenant."
            )

        # Build strict primary plan.
        if has_client_channel_preference:
            primary_plan = [ch for ch in client_requested_channels if ch in available_channels]
        else:
            # No channel preference provided by client: use router + optional AI-first ranking.
            base_plan = await self.router.select_channels(
                tenant_id=tenant_id,
                user_id=request.recipient.user_id,
                notification_type=request.notification.type,
                priority=request.notification.priority.value,
                requested_channels=available_channels,
            )
            primary_plan = [ch for ch in base_plan if ch in available_channels]
            if not primary_plan:
                primary_plan = [available_channels[0]]

            if (
                ai_on_no_channel_preference
                and llm_decision
                and llm_decision.get("channel") in primary_plan
            ):
                llm_channel = llm_decision["channel"]
                primary_plan = [llm_channel] + [ch for ch in primary_plan if ch != llm_channel]

        # Deduplicate while preserving order
        primary_plan = list(dict.fromkeys(primary_plan))

        if not primary_plan:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=(
                    "No enabled delivery channels available for this tenant and request. "
                    "Update channel settings or request different channels."
                )
            )

        # Optional AI fallback plan only after preferred client plan is exhausted.
        fallback_plan = []
        if has_client_channel_preference and ai_fallback_enabled:
            remaining = [ch for ch in available_channels if ch not in primary_plan]
            if llm_decision and llm_decision.get("channel") in remaining:
                llm_channel = llm_decision["channel"]
                remaining = [llm_channel] + [ch for ch in remaining if ch != llm_channel]
            fallback_plan = remaining

        # Strict client priority: never reorder provided preference.
        if has_client_channel_preference and strict_client_priority:
            primary_plan = [ch for ch in client_requested_channels if ch in primary_plan]

        # Avoid introducing template-required channels via AI fallback when template_id is absent.
        required_template_channels = set(channels_requiring_templates())
        if not request.notification.template_id:
            fallback_plan = [ch for ch in fallback_plan if ch not in required_template_channels]
            if not has_client_channel_preference:
                primary_plan = [ch for ch in primary_plan if ch not in required_template_channels]

        # Compose final channel plan based on execution mode.
        if delivery_mode_value == "sequential_failover":
            channel_plan = primary_plan + fallback_plan
        else:
            channel_plan = primary_plan

        selected_channels = list(dict.fromkeys(channel_plan))
        if not selected_channels:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=(
                    "No eligible delivery channels remain for this request. "
                    "Provide channels or template/channel combination that is allowed."
                )
            )

        provider_config_by_channel = await self._get_tenant_provider_config_map(tenant_id)

        recipient_field_map = {
            "email": resolved_email,
            "sms": resolved_phone,
            "whatsapp": resolved_phone,
            "slack": resolved_slack_id,
            "push": resolved_device_tokens,
            "voice": resolved_phone,
            "inapp": request.recipient.user_id,
        }
        missing_recipient_channels = []
        for channel in selected_channels:
            recipient_value = recipient_field_map.get(channel)
            if isinstance(recipient_value, list):
                recipient_present = len(recipient_value) > 0
            else:
                recipient_present = bool(recipient_value)
            if not recipient_present:
                missing_recipient_channels.append(channel)

        # Skip channels that don't have required recipient identifiers.
        # Example: request includes ["email", "sms"] but recipient only has email.
        selected_channels = [
            channel for channel in selected_channels
            if channel not in missing_recipient_channels
        ]

        if missing_recipient_channels:
            logger.warning(
                "Skipping channels without recipient details for tenant=%s user=%s: %s",
                tenant_id,
                request.recipient.user_id,
                missing_recipient_channels
            )

        if not selected_channels:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=(
                    "No deliverable channels remain after recipient validation. "
                    f"Missing recipient details for channels: {missing_recipient_channels}. "
                    "Include required recipient fields in request.recipient or request fewer channels."
                )
            )

        # Validate provider/sender config only for channels that will actually be sent.
        self._validate_tenant_sender_config(
            selected_channels=selected_channels,
            provider_config_by_channel=provider_config_by_channel
        )

        # Channels like WhatsApp require approved templates in production-style flows
        template_required_channels = channels_requiring_templates()
        channels_that_require_templates = [
            channel for channel in selected_channels
            if channel in template_required_channels
        ]
        if channels_that_require_templates and not request.notification.template_id:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"template_id is required for channels: {channels_that_require_templates}. "
                    "Create a tenant template first and pass template_id."
                )
            )

        # Create notification record with recipient info
        notification_data = dict(request.notification.data or {})
        request_fingerprint = self._build_request_fingerprint(tenant_id, request)

        # Render template if template_id is provided
        subject = request.notification.subject
        body = request.notification.body

        rendered_provider_template_refs: Dict[str, str] = {}
        if request.notification.template_id:
            # Determine channel for template lookup.
            # Prefer channels that require templates (e.g., WhatsApp).
            template_channel = (
                channels_that_require_templates[0]
                if channels_that_require_templates
                else (selected_channels[0] if selected_channels else "email")
            )

            # Render template with tenant-specific logic
            rendered = await self.tenant_template_engine.render_template(
                db=self.db,
                tenant_id=tenant_id,
                template_name=request.notification.template_id,
                channel=template_channel,
                data=notification_data,
                language="en"  # TODO: Get from user preferences
            )

            if rendered:
                # Use rendered content
                subject = rendered.get('subject') or subject
                body = rendered.get('body') or body
                if rendered.get("provider_template_ref"):
                    rendered_provider_template_refs[template_channel] = str(rendered.get("provider_template_ref"))
                logger.info(
                    f"Rendered template {request.notification.template_id} for tenant {tenant_id}"
                )
            else:
                if channels_that_require_templates:
                    raise HTTPException(
                        status_code=http_status.HTTP_400_BAD_REQUEST,
                        detail=(
                            f"Template '{request.notification.template_id}' not found/active for tenant '{tenant_id}' "
                            f"and channel '{template_channel}'."
                        )
                    )
                # Template not found - log warning but continue with provided content for non-template-required channels
                logger.warning(
                    f"Template {request.notification.template_id} not found for tenant {tenant_id}, "
                    "using provided subject/body"
                )

        provider_template_refs = self._resolve_provider_template_refs(
            template_id=request.notification.template_id,
            selected_channels=selected_channels,
            provider_config_by_channel=provider_config_by_channel
        )
        provider_template_refs.update(rendered_provider_template_refs)

        # Validate that body is not None
        if body is None:
            body = ""
            logger.warning(
                f"Notification body is None for tenant {tenant_id}, "
                f"template_id={request.notification.template_id}. Using empty string."
            )

        # Add recipient information and content to data for worker processing
        notification_data.update({
            "email": resolved_email,
            "phone": resolved_phone,
            "slack_id": resolved_slack_id,
            "device_tokens": resolved_device_tokens,
            "tenant_provider_config_by_channel": provider_config_by_channel,
            "subject": subject or "",
            "body": body,
            "template_id": request.notification.template_id,
            "template_variables": dict(request.notification.data or {}),
            "provider_template_refs": provider_template_refs,
            "delivery_mode": delivery_mode_value,
            "channel_plan": selected_channels,
            "primary_channel_plan": primary_plan,
            "fallback_channel_plan": fallback_plan,
            "skipped_channels_missing_recipient": missing_recipient_channels,
            "strict_client_priority": strict_client_priority,
            "ai_fallback_enabled": ai_fallback_enabled,
            "ai_on_no_channel_preference": ai_on_no_channel_preference,
            "has_client_channel_preference": has_client_channel_preference,
            "channel_preference_source": channel_preference_source,
            "request_fingerprint": request_fingerprint,
        })

        notification = Notification(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            user_id=request.recipient.user_id,
            type=request.notification.type,
            priority=priority_map[request.notification.priority],
            status=NotificationStatus.QUEUED,
            template_id=request.notification.template_id,
            data=notification_data,
            scheduled_at=None,  # For immediate delivery
            llm_decision=llm_decision,  # NEW: Store AI decision
            idempotency_key=idempotency_key,  # Use the variable we extracted earlier
            owner_id=owner_id if owner_id else None
        )

        self.db.add(notification)
        await self.db.flush()

        # Create notification channel records
        channels_response = {}
        for channel_name in selected_channels:
            channel = NotificationChannel(
                id=uuid.uuid4(),
                notification_id=notification.id,
                channel=channel_name,
                provider=self._get_provider_for_channel(channel_name),
                status=ChannelStatus.QUEUED,
                attempts=0,
            )
            self.db.add(channel)

            channels_response[channel_name] = {
                "channel": channel_name,
                "provider": channel.provider,
                "message_id": None,
                "status": "queued",
                "delivered_at": None,
                "opened_at": None,
                "clicked_at": None,
            }

        await self.db.commit()

        # Store idempotency key in Redis cache (if provided)
        if idempotency_key:
            try:
                from src.core import get_redis_client
                from src.utils.deduplication import DeduplicationService

                redis = await get_redis_client()
                dedup = DeduplicationService(redis)
                await dedup.store_idempotency_key(
                    idempotency_key,
                    str(notification.id),
                    ttl=86400  # 24 hours
                )
                logger.info(f"Stored idempotency key for notification {notification.id}")
            except Exception as e:
                logger.error(f"Failed to store idempotency key: {e}")

        # Increment tenant usage counter
        await usage_tracker.increment_usage(tenant_id)

        # === NEW: Queue notification for async processing ===
        try:
            from src.tasks.notification_tasks import (
                send_notification_critical,
                send_notification_high,
                send_notification_medium,
                send_notification_low
            )

            # Map priority to task
            priority_tasks = {
                'critical': send_notification_critical,
                'high': send_notification_high,
                'medium': send_notification_medium,
                'low': send_notification_low
            }

            priority_value = request.notification.priority.value
            task = priority_tasks.get(priority_value, send_notification_medium)

            # Queue task asynchronously
            task.apply_async(args=[str(notification.id)])

            logger.info(
                f"Queued notification {notification.id} with priority {priority_value}"
            )

        except Exception as e:
            logger.error(f"Failed to queue notification: {e}")
            # Continue anyway - notification is in database

        return NotificationResponse(
            notification_id=str(notification.id),
            status=NotificationStatus.QUEUED,
            channels=channels_response,
            estimated_delivery=datetime.utcnow(),
            created_at=notification.created_at,
        )

    async def send_batch_notifications(
        self, tenant_id: str, request: BatchNotificationRequest, owner_id: str | None = None
    ) -> BatchNotificationResponse:
        """
        Send notifications to multiple recipients in batch.

        Args:
            request: Batch notification request

        Returns:
            BatchNotificationResponse with batch ID and status
        """
        batch_id = str(uuid.uuid4())
        
        # Check tenant quota before anything else
        from fastapi import HTTPException, status as http_status
        from sqlalchemy import select
        
        allowed, usage_info = await usage_tracker.check_quota(self.db, tenant_id)
        if not allowed:
            raise HTTPException(
                status_code=http_status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Monthly quota exceeded. Used: {usage_info['used']}/{usage_info['quota']}. "
                       f"Resets on: {usage_info['reset_date']}"
            )
            
        # Also limit the number of recipients in a single batch request
        if len(request.recipients) > 100:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="Batch request too large. Maximum 100 recipients allowed per request."
            )
            
        # === Idempotency Check ===
        idempotency_key = getattr(request, 'idempotency_key', None)
        if idempotency_key:
            try:
                from src.core import get_redis_client
                from src.utils.deduplication import DeduplicationService

                redis = await get_redis_client()
                dedup = DeduplicationService(redis)
                existing_id = await dedup.check_idempotency_key(idempotency_key)

                if existing_id:
                    logger.info(f"Duplicate batch detected in Redis cache: {idempotency_key}")
                    # Return the existing batch ID
                    return BatchNotificationResponse(
                        batch_id=existing_id,
                        status="queued",
                        recipients_count=len(request.recipients),
                        estimated_completion=datetime.utcnow()
                    )
                else:
                    await dedup.store_idempotency_key(idempotency_key, batch_id)
            except Exception as e:
                logger.warning(f"Redis idempotency check failed: {e}")

        # Fallback deduplication: Check request fingerprint if no idempotency key provided
        if not idempotency_key:
            request_fingerprint = self._build_batch_request_fingerprint(tenant_id, request)
            existing_recent_id = await self._find_recent_duplicate_by_fingerprint(
                tenant_id=tenant_id,
                fingerprint=request_fingerprint,
                window_minutes=10,
            )
            if existing_recent_id:
                logger.info(f"Duplicate batch detected via request fingerprint for tenant={tenant_id}")
                return BatchNotificationResponse(
                    batch_id=existing_recent_id,
                    status="queued",
                    recipients_count=len(request.recipients),
                    estimated_completion=datetime.utcnow()
                )
            # If not a duplicate, we will still assign a new batch_id below
            try:
                from src.core import get_redis_client
                redis = await get_redis_client()
                key = f"fingerprint:{tenant_id}:{request_fingerprint}"
                await redis.setex(key, 600, batch_id) # 10 minutes TTL
            except Exception as e:
                logger.warning(f"Failed to store request fingerprint in Redis: {e}")

        batch_id = str(uuid.uuid4())

        selected_channel = request.channel.value
        template_required_channels = channels_requiring_templates()
        provider_config_by_channel = await self._get_tenant_provider_config_map(tenant_id)

        self._validate_tenant_sender_config(
            selected_channels=[selected_channel],
            provider_config_by_channel=provider_config_by_channel
        )

        if selected_channel in template_required_channels and not request.template_id:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=f"template_id is required for channel '{selected_channel}'."
            )

        if not request.template_id and not request.body:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="Either template_id or body is required for batch sends."
            )

        # Create notifications for each recipient
        notification_ids = []
        for recipient in request.recipients:
            base_data = dict(request.data or {})
            base_data.update(recipient.data or {})

            subject = request.subject
            body = request.body
            provider_template_refs = self._resolve_provider_template_refs(
                template_id=request.template_id,
                selected_channels=[selected_channel],
                provider_config_by_channel=provider_config_by_channel
            )
            if request.template_id:
                rendered = await self.tenant_template_engine.render_template(
                    db=self.db,
                    tenant_id=tenant_id,
                    template_name=request.template_id,
                    channel=selected_channel,
                    data=base_data,
                    language="en"
                )
                if not rendered:
                    raise HTTPException(
                        status_code=http_status.HTTP_400_BAD_REQUEST,
                        detail=(
                            f"Template '{request.template_id}' not found/active for tenant '{tenant_id}' "
                            f"and channel '{selected_channel}'."
                        )
                    )
                subject = rendered.get("subject") or subject
                body = rendered.get("body") or body
                if rendered.get("provider_template_ref"):
                    provider_template_refs[selected_channel] = str(rendered.get("provider_template_ref"))

            notification_data = self._build_batch_recipient_data(recipient)
            notification_data.update({
                **base_data,
                "tenant_provider_config_by_channel": provider_config_by_channel,
                "subject": subject or "",
                "body": body or "",
                "template_id": request.template_id,
                "template_variables": base_data,
                "provider_template_refs": provider_template_refs,
                "channel_plan": [selected_channel],
                "primary_channel_plan": [selected_channel],
                "fallback_channel_plan": [],
                "delivery_mode": "parallel_all",
                "request_fingerprint": request_fingerprint if not idempotency_key else None,
            })

            notification = Notification(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                user_id=recipient.user_id,
                type="batch_notification",
                priority=DBPriority.MEDIUM,
                status=NotificationStatus.QUEUED,
                template_id=request.template_id,
                data=notification_data,
                scheduled_at=request.schedule_at,
                owner_id=owner_id if owner_id else None
            )
            self.db.add(notification)
            notification_ids.append(str(notification.id))

            channel = NotificationChannel(
                id=uuid.uuid4(),
                notification_id=notification.id,
                channel=selected_channel,
                provider=self._get_provider_for_channel(selected_channel),
                status=ChannelStatus.QUEUED,
                attempts=0,
            )
            self.db.add(channel)

        await self.db.commit()

        # Queue batch for processing
        if not request.schedule_at:
            from src.tasks.notification_tasks import send_notification_medium
            queued_count = 0
            for nid in notification_ids:
                try:
                    send_notification_medium.apply_async(args=[nid], priority=5)
                    queued_count += 1
                except Exception as e:
                    logger.error(f"Failed to queue batch notification {nid}: {e}")
            logger.info(f"Queued {queued_count}/{len(notification_ids)} notifications for batch processing")

        return BatchNotificationResponse(
            batch_id=batch_id,
            status="processing",
            total_recipients=len(request.recipients),
            estimated_completion=request.schedule_at or datetime.utcnow(),
        )

    async def send_batch_notifications_multichannel(
        self, tenant_id: str, request: BatchMultiChannelNotificationRequest, owner_id: str | None = None
    ) -> BatchMultiChannelNotificationResponse:
        """
        Send notifications to multiple recipients across multiple channels.
        """
        batch_id = str(uuid.uuid4())
        
        # Check tenant quota before anything else
        from fastapi import HTTPException, status as http_status
        from sqlalchemy import select
        
        allowed, usage_info = await usage_tracker.check_quota(self.db, tenant_id)
        if not allowed:
            raise HTTPException(
                status_code=http_status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Monthly quota exceeded. Used: {usage_info['used']}/{usage_info['quota']}. "
                       f"Resets on: {usage_info['reset_date']}"
            )
            
        # Also limit the number of recipients in a single batch request
        if len(request.recipients) > 100:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="Batch request too large. Maximum 100 recipients allowed per request."
            )
            
        # === Idempotency Check ===
        idempotency_key = getattr(request, 'idempotency_key', None)
        if idempotency_key:
            try:
                from src.core import get_redis_client
                from src.utils.deduplication import DeduplicationService

                redis = await get_redis_client()
                dedup = DeduplicationService(redis)
                existing_id = await dedup.check_idempotency_key(idempotency_key)

                if existing_id:
                    logger.info(f"Duplicate multichannel batch detected in Redis cache: {idempotency_key}")
                    # Return the existing batch ID
                    return BatchMultiChannelNotificationResponse(
                        batch_id=existing_id,
                        status="queued",
                        recipients_count=len(request.recipients),
                        estimated_completion=datetime.utcnow()
                    )
                else:
                    await dedup.store_idempotency_key(idempotency_key, batch_id)
            except Exception as e:
                logger.warning(f"Redis idempotency check failed: {e}")

        # Fallback deduplication: Check request fingerprint if no idempotency key provided
        if not idempotency_key:
            request_fingerprint = self._build_batch_request_fingerprint(tenant_id, request)
            import logging
            logging.getLogger(__name__).info(f"Using request fingerprint for dedup: {request_fingerprint}")
            existing_recent_id = await self._find_recent_duplicate_by_fingerprint(
                tenant_id=tenant_id,
                fingerprint=request_fingerprint,
                window_minutes=10,
            )
            if existing_recent_id:
                logger.info(f"Duplicate multichannel batch detected via request fingerprint for tenant={tenant_id}")
                return BatchMultiChannelNotificationResponse(
                    batch_id=existing_recent_id,
                    status="queued",
                    recipients_count=len(request.recipients),
                    estimated_completion=datetime.utcnow()
                )
                
            # Store the current batch id as reference for fingerprint if not dup
            try:
                from src.core import get_redis_client
                redis = await get_redis_client()
                key = f"fingerprint:{tenant_id}:{request_fingerprint}"
                await redis.setex(key, 600, batch_id) # 10 minutes TTL
            except Exception as e:
                logger.warning(f"Failed to store request fingerprint in Redis: {e}")

        requested_channels = list(dict.fromkeys([c.value for c in request.channels]))
        tenant_row = await self.db.get(Tenant, tenant_id)
        tenant_config = (tenant_row.config or {}) if tenant_row else {}
        tenant_default_delivery_mode = tenant_config.get("default_delivery_mode") or "parallel_all"
        if tenant_default_delivery_mode not in {"parallel_all", "sequential_failover"}:
            tenant_default_delivery_mode = "parallel_all"
        delivery_mode = request.delivery_mode.value if getattr(request, "delivery_mode", None) else tenant_default_delivery_mode
        strict_client_priority = getattr(request, "strict_client_priority", True)
        ai_fallback_enabled = getattr(request, "ai_fallback_enabled", True)
        ai_on_no_channel_preference = getattr(request, "ai_on_no_channel_preference", True)

        # Enforce tenant-level channel preferences.
        prefs_result = await self.db.execute(
            select(TenantChannelPreference).where(TenantChannelPreference.tenant_id == tenant_id)
        )
        prefs = prefs_result.scalars().all()
        enabled_map = {p.channel: p.enabled for p in prefs} if prefs else {}

        def _is_enabled(channel: str) -> bool:
            return enabled_map.get(channel, True) if enabled_map else True

        supported_channels = ["email", "sms", "whatsapp", "slack", "voice"] # "push", "inapp"]
        available_channels = [ch for ch in supported_channels if _is_enabled(ch)]
        if not available_channels:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="No delivery channels are enabled for this tenant."
            )

        has_client_channel_preference = len(requested_channels) > 0
        if (
            has_client_channel_preference
            and "whatsapp" in requested_channels
            and not request.template_id
        ):
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="template_id is required when requesting whatsapp channel."
            )

        total_notifications = 0
        total_channel_records = 0
        used_channels: set[str] = set()
        provider_config_by_channel = await self._get_tenant_provider_config_map(tenant_id)

        # Channels requiring templates should not appear without template_id or channel_template_map
        required_template_channels = set(channels_requiring_templates())
        has_any_template = bool(request.template_id or (getattr(request, 'channel_template_map', None)))
        has_any_body = bool(request.body or (getattr(request, 'channel_body_map', None)))

        if not has_any_template and not has_any_body:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="Either template_id, body, channel_template_map, or channel_body_map is required for batch-multichannel requests."
            )

        notification_ids = []
        for recipient in request.recipients:
            # Build primary plan per recipient
            if has_client_channel_preference:
                primary_plan = [ch for ch in requested_channels if ch in available_channels]
            else:
                if ai_on_no_channel_preference:
                    router_channels = await self.router.select_channels(
                        tenant_id=tenant_id,
                        user_id=recipient.user_id,
                        notification_type="batch_notification",
                        priority="medium",
                        requested_channels=available_channels,
                    )
                    primary_plan = [ch for ch in router_channels if ch in available_channels]
                else:
                    primary_plan = [available_channels[0]]

            primary_plan = list(dict.fromkeys(primary_plan))

            if has_client_channel_preference and strict_client_priority:
                primary_plan = [ch for ch in requested_channels if ch in primary_plan]

            fallback_plan = []
            if has_client_channel_preference and ai_fallback_enabled:
                fallback_plan = [ch for ch in available_channels if ch not in primary_plan]

            # Protect template-required channels if template_id missing (defensive)
            channel_template_map_val = getattr(request, 'channel_template_map', None) or {}
            
            def has_template_for_ch(c):
                return bool(request.template_id or channel_template_map_val.get(c))

            primary_plan = [ch for ch in primary_plan if ch not in required_template_channels or has_template_for_ch(ch)]
            fallback_plan = [ch for ch in fallback_plan if ch not in required_template_channels or has_template_for_ch(ch)]

            channel_plan = primary_plan + fallback_plan if delivery_mode == "sequential_failover" else primary_plan
            selected_channels = list(dict.fromkeys(channel_plan))
            if not selected_channels:
                continue

            self._validate_tenant_sender_config(
                selected_channels=selected_channels,
                provider_config_by_channel=provider_config_by_channel
            )

            per_recipient_template_vars = dict(request.data or {})
            per_recipient_template_vars.update(recipient.data or {})
            subject = request.subject
            body = request.body

            # Support for channel-specific templates/content
            channel_template_map = getattr(request, 'channel_template_map', None) or {}
            channel_subject_map = getattr(request, 'channel_subject_map', None) or {}
            channel_body_map = getattr(request, 'channel_body_map', None) or {}

            channel_content_map = {}
            rendered_provider_template_refs = {}

            for ch in selected_channels:
                ch_template_id = channel_template_map.get(ch) or request.template_id
                ch_subject = channel_subject_map.get(ch) or subject
                ch_body = channel_body_map.get(ch) or body

                if ch_template_id:
                    rendered = await self.tenant_template_engine.render_template(
                        db=self.db,
                        tenant_id=tenant_id,
                        template_name=ch_template_id,
                        channel=ch,
                        data=per_recipient_template_vars,
                        language="en"
                    )
                    if not rendered:
                        raise HTTPException(
                            status_code=http_status.HTTP_400_BAD_REQUEST,
                            detail=(
                                f"Template '{ch_template_id}' not found/active for tenant '{tenant_id}' "
                                f"and channel '{ch}'."
                            )
                        )
                    ch_subject = rendered.get("subject") or ch_subject
                    ch_body = rendered.get("body") or ch_body
                    if rendered.get("provider_template_ref"):
                        rendered_provider_template_refs[ch] = str(rendered.get("provider_template_ref"))
                
                channel_content_map[ch] = {
                    "subject": ch_subject,
                    "body": ch_body,
                    "template_id": ch_template_id
                }

            # If no channel override exists, just use the global fallback one
            if not channel_content_map.get(selected_channels[0] if selected_channels else "email"):
                pass

            provider_template_refs = self._resolve_provider_template_refs(
                template_id=request.template_id,
                selected_channels=selected_channels,
                provider_config_by_channel=provider_config_by_channel
            )
            provider_template_refs.update(rendered_provider_template_refs)

            notification_data = self._build_batch_recipient_data(recipient)
            notification_data.update({
                "tenant_provider_config_by_channel": provider_config_by_channel,
                "subject": subject or "",
                "body": body or "",
                "template_id": request.template_id,
                "channel_content_map": channel_content_map,
                "template_variables": per_recipient_template_vars,
                **per_recipient_template_vars,
                "provider_template_refs": provider_template_refs,
                "delivery_mode": delivery_mode,
                "channel_plan": selected_channels,
                "primary_channel_plan": primary_plan,
                "fallback_channel_plan": fallback_plan,
                "strict_client_priority": strict_client_priority,
                "ai_fallback_enabled": ai_fallback_enabled,
                "ai_on_no_channel_preference": ai_on_no_channel_preference,
                "has_client_channel_preference": has_client_channel_preference,
            })
            notification = Notification(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                user_id=recipient.user_id,
                type="batch_notification",
                priority=DBPriority.MEDIUM,
                status=NotificationStatus.QUEUED,
                template_id=request.template_id,
                data=notification_data,
                scheduled_at=request.schedule_at,
                owner_id=owner_id if owner_id else None
            )
            self.db.add(notification)
            notification_ids.append(str(notification.id))
            total_notifications += 1

            for channel_name in selected_channels:
                channel = NotificationChannel(
                    id=uuid.uuid4(),
                    notification_id=notification.id,
                    channel=channel_name,
                    provider=self._get_provider_for_channel(channel_name),
                    status=ChannelStatus.QUEUED,
                    attempts=0,
                )
                self.db.add(channel)
                total_channel_records += 1
                used_channels.add(channel_name)

        await self.db.commit()

        # Queue multi-channel batch for processing
        if not request.schedule_at:
            from src.tasks.notification_tasks import send_notification_medium
            queued_count = 0
            
            # Use a slightly different execution approach to force immediate execution
            # rather than dumping all of them into the queue at once, especially for solo pools
            for nid in notification_ids:
                try:
                    # In a production environment, applying async is fine.
                    # But if we want to ensure it doesn't get stuck in the queue when running
                    # in environments with limited concurrency, we can use a slight delay
                    # or force the current event loop to yield. 
                    # For now, we still push to celery, but we let celery handle the sequence.
                    send_notification_medium.apply_async(args=[nid], priority=5)
                    queued_count += 1
                except Exception as e:
                    logger.error(f"Failed to queue multi-channel batch notification {nid}: {e}")
            logger.info(f"Queued {queued_count}/{len(notification_ids)} multi-channel notifications for batch processing")

        return BatchMultiChannelNotificationResponse(
            batch_id=batch_id,
            status="processing",
            total_recipients=len(request.recipients),
            total_notifications=total_notifications,
            total_channel_records=total_channel_records,
            channels=sorted(list(used_channels)),
            estimated_completion=request.schedule_at or datetime.utcnow(),
        )

    def _get_provider_for_channel(self, channel: str) -> str:
        """Get the provider name for a channel."""
        return get_provider_for_channel(channel)

    async def _get_tenant_provider_config_map(self, tenant_id: str) -> Dict[str, Dict[str, Any]]:
        """Load active tenant provider config keyed by channel/provider name."""
        query = select(TenantProviderConfig).where(
            TenantProviderConfig.tenant_id == tenant_id,
            TenantProviderConfig.is_active == True,
        )
        result = await self.db.execute(query)
        rows = result.scalars().all()
        return {row.provider: (row.config or {}) for row in rows}

    def _validate_tenant_sender_config(
        self,
        selected_channels: list[str],
        provider_config_by_channel: Dict[str, Dict[str, Any]],
    ) -> None:
        """Enforce tenant-owned sender identities for outbound channels."""
        required_sender_channels = {"email", "sms", "whatsapp", "voice"}
        missing = []

        logger.info(f"Validating sender config for channels: {selected_channels}")
        logger.info(f"Available provider configs: {list(provider_config_by_channel.keys())}")

        for channel in selected_channels:
            if channel not in required_sender_channels:
                continue
            
            cfg = provider_config_by_channel.get(channel) or {}
            logger.info(f"Config for {channel}: {cfg}")
            
            sender = cfg.get("from_email") or cfg.get("sender_email") or cfg.get("from_number") or cfg.get("sender_id")
            if not sender:
                missing.append(channel)

        if missing:
            logger.warning(f"Missing sender identity for: {missing}. Available configs: {list(provider_config_by_channel.keys())}")
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Tenant sender identity is not configured for channels: {missing}. "
                    f"Available configs: {list(provider_config_by_channel.keys())}. "
                    "Configure sender under tenant provider settings before sending."
                ),
            )

    def _build_batch_recipient_data(self, recipient) -> Dict[str, Any]:
        """Normalize recipient contact payload for batch notification records."""
        base_data = recipient.data or {}
        base_data.update({
            "email": recipient.email,
            "phone": recipient.phone,
            "slack_id": getattr(recipient, "slack_id", None),
            "device_tokens": getattr(recipient, "device_tokens", None),
        })
        return base_data

    def _resolve_provider_template_refs(
        self,
        template_id: str | None,
        selected_channels: list[str],
        provider_config_by_channel: Dict[str, Dict[str, Any]],
    ) -> Dict[str, str]:
        """
        Resolve internal template_id to provider-native template refs per channel.

        Mapping source is tenant provider config:
        {
          "template_refs": {
            "<internal_template_id>": "<provider_template_ref>"
          }
        }
        """
        if not template_id:
            return {}

        refs: Dict[str, str] = {}
        for channel in selected_channels:
            cfg = provider_config_by_channel.get(channel) or {}
            template_refs = cfg.get("template_refs") or {}
            if not isinstance(template_refs, dict):
                continue
            provider_ref = template_refs.get(template_id)
            if provider_ref:
                refs[channel] = str(provider_ref)
        return refs
