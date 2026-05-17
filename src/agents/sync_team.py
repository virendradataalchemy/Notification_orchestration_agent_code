"""Synchronous notification processing team."""
from typing import Dict, Any
import logging
import json
from src.agents.notification_agents import (
    create_analyzer_agent,
    create_router_agent
)

logger = logging.getLogger(__name__)


class NotificationTeam:
    """
    Synchronous team for notification processing.

    Flow: Analyzer → Router (sequential, fast)
    NO Learner in sync flow - learning happens asynchronously via webhooks

    The team returns immediately after sending the notification.
    Outcome tracking and learning happen later via webhook callbacks.
    """

    def __init__(self):
        logger.info("Initializing NotificationTeam")

        # Create agents
        self.analyzer = create_analyzer_agent()  # Haiku - cheap & fast
        self.router = create_router_agent()      # Sonnet - smart decisions

        logger.info("NotificationTeam initialized successfully")

    async def process_notification(
        self,
        tenant_id: str,
        user_id: str,
        notification_type: str,
        content: str,
        priority: str,
        metadata: Dict[str, Any] = None,
        owner_id: Any = None
    ) -> Dict[str, Any]:
        """
        Process notification synchronously (fast response < 1s).

        Returns immediately after sending, doesn't wait for outcome.

        Args:
            tenant_id: Tenant identifier
            user_id: User identifier
            notification_type: Type of notification
            content: Notification content
            priority: Priority level (critical, high, medium, low)
            metadata: Additional metadata
            owner_id: The team member ID who initiated this

        Returns:
            Processing result with notification ID, channel, and status
        """
        logger.info(
            f"Processing notification: user={user_id}, "
            f"type={notification_type}, priority={priority}, owner={owner_id}"
        )
        
        # Add owner_id to metadata if present so tools can access it
        if owner_id:
            if metadata is None:
                metadata = {}
            metadata["owner_id"] = str(owner_id)

        # STEP 1: Analyzer Agent
        analyzer_task = f"""
Analyze this notification request:

**User:** {user_id}
**Type:** {notification_type}
**Priority:** {priority}
**Content:** {content[:200]}{"..." if len(content) > 200 else ""}

**YOUR TASKS:**
1. Use `check_for_duplicate` tool to check if this is a duplicate
2. If duplicate is found, immediately return:
   {{"is_duplicate": true, "stop": true, "reason": "...", "existing_id": "..."}}
3. If NOT duplicate, gather context:
   - Use `get_user_engagement_history` tool
   - Use `get_user_preferences` tool
   - Use `query_similar_past_notifications` tool (this queries ChromaDB memory)
4. Return analysis with user context

**IMPORTANT:** If duplicate found, stop immediately with stop=true!
This prevents wasting resources on Router agent.
"""

        try:
            # Run Analyzer
            analysis_response = await self.analyzer.invoke_async(analyzer_task)

            # Parse response (could be string or object)
            if hasattr(analysis_response, 'content'):
                analysis_text = analysis_response.content
            else:
                analysis_text = str(analysis_response)

            # Try to parse as JSON
            try:
                analysis_result = json.loads(analysis_text)
            except:
                analysis_result = {"analysis": analysis_text}

            # Check for early termination (duplicate detected)
            if isinstance(analysis_result, dict):
                if analysis_result.get("is_duplicate") or analysis_result.get("stop"):
                    logger.info(
                        f"Duplicate detected: {analysis_result.get('reason')} - "
                        f"stopping processing"
                    )
                    return {
                        "status": "duplicate",
                        "reason": analysis_result.get("reason"),
                        "existing_id": "already_sent",
                        "processing_stopped": True
                    }

        except Exception as e:
            logger.error(f"Analyzer failed: {e}", exc_info=True)
            # Don't block notification on analyzer failure - use fallback
            analysis_result = {
                "error": str(e),
                "use_fallback": True,
                "engagement_history": {},
                "preferences": {},
                "similar_notifications": []
            }

        # STEP 2: Router Agent (only if not duplicate)
        router_task = f"""
Route this notification to the best channel:

**User:** {user_id}
**Tenant:** {tenant_id}
**Type:** {notification_type}
**Priority:** {priority}
**Content:** {content[:200]}

**Analysis from Analyzer Agent:**
{analysis_result}

**YOUR TASKS:**
1. Use `check_provider_health` tool to get provider status
2. Use `predict_best_channel` tool - it will:
   - Learn from similar past notifications (from ChromaDB memory)
   - Consider user engagement patterns
   - Apply fallback heuristics if needed (cold start)
3. Use `check_quiet_hours` tool to check timing
4. If quiet hours and not critical:
   - Consider delaying OR using silent channels (email, in-app)
5. Use `send_notification_via_channel` tool to send notification
6. Return notification_id, channel, and reasoning

**Make the best decision** based on memory, data, and context!
Explain your reasoning clearly.
"""

        try:
            # Run Router
            routing_response = await self.router.invoke_async(router_task)

            # Parse response (could be string or object)
            if hasattr(routing_response, 'content'):
                routing_text = routing_response.content
            else:
                routing_text = str(routing_response)

            # Try to parse as JSON
            try:
                routing_result = json.loads(routing_text)
            except:
                routing_result = {"routing": routing_text}

            logger.info(
                f"Notification sent: {routing_result.get('notification_id')} "
                f"via {routing_result.get('channel')}"
            )

            return {
                "status": "sent",
                "notification_id": routing_result.get("notification_id"),
                "channel": routing_result.get("channel"),
                "analysis": analysis_result,
                "routing": routing_result
            }

        except Exception as e:
            logger.error(f"Router failed: {e}", exc_info=True)
            raise


# Singleton instance
_team = None


def get_notification_team() -> NotificationTeam:
    """Get singleton notification team instance."""
    global _team
    if _team is None:
        _team = NotificationTeam()
    return _team
