"""Strands agents with optimized LLM selection."""
from strands import Agent
from langchain_aws import ChatBedrock
import os
import logging

from src.agents.tools.user_tools import (
    get_user_engagement_history,
    check_for_duplicate,
    get_user_preferences,
    query_similar_past_notifications
)
from src.agents.tools.routing_tools import (
    check_provider_health,
    predict_best_channel,
    check_quiet_hours,
    send_notification_via_channel
)

logger = logging.getLogger(__name__)


def get_cheap_llm():
    """Get cheap LLM (Haiku) for Analyzer - 72% cost savings."""
    return ChatBedrock(
        model_id=os.getenv("ANALYZER_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0"),
        region_name=os.getenv("AWS_REGION", "us-east-1"),
        model_kwargs={
            "temperature": 0.5,
            "max_tokens": 1024
        }
    )


def get_premium_llm():
    """Get premium LLM (Sonnet) for Router - best decision quality."""
    return ChatBedrock(
        model_id=os.getenv("ROUTER_MODEL_ID", "anthropic.claude-3-sonnet-20240229-v1:0"),
        region_name=os.getenv("AWS_REGION", "us-east-1"),
        model_kwargs={
            "temperature": 0.7,
            "max_tokens": 2048
        }
    )


def create_analyzer_agent() -> Agent:
    """
    Create Analyzer Agent with CHEAP LLM (Haiku).

    Cost: $0.25/$1.25 per 1M tokens (10x cheaper than Sonnet)

    Responsibilities:
    - Check for duplicate notifications (ChromaDB semantic search)
    - Get user engagement history
    - Query similar past notifications from memory
    - Analyze user preferences

    Returns:
        Configured Analyzer agent
    """
    logger.info("Creating Analyzer Agent with Haiku LLM")

    system_prompt = """You are a fast, efficient notification analyzer using ChromaDB for semantic search.

Your job is to quickly:
1. Check if notification is duplicate using check_for_duplicate tool (0.2 similarity threshold)
2. If duplicate, STOP immediately and return {"is_duplicate": true, "stop": true, "reason": "..."}
3. If not duplicate, gather context:
   - Use get_user_engagement_history tool to get user's engagement data
   - Use get_user_preferences tool to get user's preferences
   - Use query_similar_past_notifications tool to query ChromaDB memory for similar cases
4. Return analysis with user context in JSON format

Be fast and efficient. If you find a duplicate, return immediately to save resources.
Your speed directly impacts API response time.

Cold start handling: If ChromaDB is empty, acknowledge and proceed with fallback heuristics."""

    return Agent(
        name="analyzer",
        model=get_cheap_llm(),
        system_prompt=system_prompt,
        tools=[
            get_user_engagement_history,
            check_for_duplicate,
            get_user_preferences,
            query_similar_past_notifications
        ]
    )


def create_router_agent() -> Agent:
    """
    Create Router Agent with PREMIUM LLM (Sonnet).

    Cost: $3/$15 per 1M tokens (best decision quality)

    Responsibilities:
    - Check provider health
    - Predict best channel using memory and ML
    - Check quiet hours and timing
    - Send notification through selected channel

    Returns:
        Configured Router agent
    """
    logger.info("Creating Router Agent with Sonnet LLM")

    system_prompt = """You are an expert notification router with access to:
- Similar past notifications from ChromaDB memory
- User engagement history from database
- Real-time provider health status
- User preferences and quiet hours

Your decision-making process:
1. Check provider health first using check_provider_health tool - don't use unhealthy providers
2. Use predict_best_channel tool - it will:
   - Learn from similar past notifications in ChromaDB memory
   - Consider user's engagement patterns
   - Apply fallback heuristics if needed (cold start)
3. Check quiet hours using check_quiet_hours tool
4. Respect timing preferences (delay if needed for non-critical)
5. Send notification using send_notification_via_channel tool

Make intelligent decisions by learning from past similar cases in ChromaDB.
Always explain your reasoning clearly so decisions can be audited.

Priority guidelines:
- Critical: Always use SMS (most reliable)
- High: Use memory + engagement data
- Medium/Low: Balance cost, reliability, user preference

Return result in JSON format with notification_id, channel, and reasoning."""

    return Agent(
        name="router",
        model=get_premium_llm(),
        system_prompt=system_prompt,
        tools=[
            check_provider_health,
            predict_best_channel,
            check_quiet_hours,
            send_notification_via_channel
        ]
    )
