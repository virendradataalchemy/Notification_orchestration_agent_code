"""Asynchronous learner agent (NO LLM - pure logic)."""
from typing import Dict, Any
import logging
from datetime import datetime
import boto3
import json
import os
from src.agents.memory import get_agent_memory
from src.services.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)


class AsyncLearnerAgent:
    """
    Asynchronous learning agent (NO LLM needed).

    Triggered by webhooks when notification outcomes arrive.
    Uses pure logic for reward calculation and storage.

    Stores outcomes in:
    - ChromaDB (for agent memory / similarity search)
    - S3 (for batch ML model retraining)
    """

    def __init__(self):
        self.memory = get_agent_memory()
        self.embeddings = EmbeddingService()
        self.s3 = boto3.client('s3')
        self.sagemaker = boto3.client('sagemaker')
        self.ml_bucket = os.getenv("ML_BUCKET", "notification-ml-data")
        self.pipeline_name = os.getenv("SAGEMAKER_PIPELINE", "notification-ml-retraining")

    async def record_outcome(
        self,
        notification_id: str,
        user_id: str,
        channel: str,
        notification_type: str,
        priority: str,
        outcome: Dict[str, Any]
    ):
        """
        Record notification outcome and learn from it.

        Called by webhook handler when outcome arrives (minutes/hours later).
        Pure logic - no LLM calls needed.

        Args:
            notification_id: Notification identifier
            user_id: User identifier
            channel: Channel used
            notification_type: Type of notification
            priority: Priority level
            outcome: Outcome data (delivered, opened, clicked, failed)
        """
        logger.info(f"Recording outcome: {notification_id}, event={outcome.get('event')}")

        # Calculate reward (pure logic, no LLM)
        reward = self._calculate_reward(outcome)

        # Create decision text for embedding
        decision_text = self._create_decision_text(
            user_id, channel, notification_type, priority, outcome, reward
        )

        # Generate embedding
        embedding = self.embeddings.generate_embedding(decision_text)

        # Store in ChromaDB (for agent memory)
        self.memory.store_decision(
            notification_id=notification_id,
            decision_text=decision_text,
            embedding=embedding,
            metadata={
                "user_id": user_id,
                "channel": channel,
                "notification_type": notification_type,
                "priority": priority,
                "reward": reward,
                "delivered": outcome.get("delivered", False),
                "opened": outcome.get("opened", False),
                "clicked": outcome.get("clicked", False),
                "failed": outcome.get("failed", False),
                "timestamp": datetime.utcnow().isoformat()
            }
        )

        # Store in S3 (for batch ML retraining)
        await self._store_in_s3(
            notification_id, user_id, channel, notification_type,
            priority, outcome, reward
        )

        # Check if retraining threshold reached
        if await self._should_retrain():
            await self._trigger_retraining()

        logger.info(f"Outcome recorded: notification={notification_id}, reward={reward}")

        return {"reward": reward, "stored": True}

    def _calculate_reward(self, outcome: Dict[str, Any]) -> float:
        """
        Calculate reward using pure logic (no LLM).

        Reward components:
        - Delivered: +1.0
        - Opened: +2.0
        - Clicked: +3.0
        - Fast delivery (< 60s): +0.5
        - Medium speed (< 300s): +0.2
        - Channel cost: -0.001 to -0.10
        - Failed: -2.0
        """
        reward = 0.0

        # Base rewards
        if outcome.get("delivered"):
            reward += 1.0
        if outcome.get("opened"):
            reward += 2.0
        if outcome.get("clicked"):
            reward += 3.0

        # Speed bonus
        delivery_time = outcome.get("delivery_time_seconds", 999)
        if delivery_time < 60:
            reward += 0.5
        elif delivery_time < 300:
            reward += 0.2

        # Cost penalty
        channel = outcome.get("channel", "email")
        channel_costs = {
            "email": 0.001,
            "sms": 0.05,
            "whatsapp": 0.03,
            "push": 0.01,
            "slack": 0.005,
            "voice": 0.10,
            "inapp": 0.0
        }
        reward -= channel_costs.get(channel, 0)

        # Failure penalty
        if outcome.get("failed"):
            reward -= 2.0

        return reward

    def _create_decision_text(
        self,
        user_id: str,
        channel: str,
        notification_type: str,
        priority: str,
        outcome: Dict[str, Any],
        reward: float
    ) -> str:
        """Create text representation for embedding."""
        return f"""
User: {user_id}
Type: {notification_type}
Priority: {priority}
Channel: {channel}
Delivered: {outcome.get('delivered', False)}
Opened: {outcome.get('opened', False)}
Clicked: {outcome.get('clicked', False)}
Reward: {reward:.2f}
Timestamp: {datetime.utcnow().isoformat()}
        """.strip()

    async def _store_in_s3(
        self,
        notification_id: str,
        user_id: str,
        channel: str,
        notification_type: str,
        priority: str,
        outcome: Dict[str, Any],
        reward: float
    ):
        """Store experience in S3 for batch ML retraining."""
        try:
            experience = {
                "notification_id": notification_id,
                "user_id": user_id,
                "channel": channel,
                "notification_type": notification_type,
                "priority": priority,
                "outcome": outcome,
                "reward": reward,
                "timestamp": datetime.utcnow().isoformat()
            }

            key = f"experiences/{datetime.utcnow().date()}/{notification_id}.json"

            self.s3.put_object(
                Bucket=self.ml_bucket,
                Key=key,
                Body=json.dumps(experience)
            )

            logger.debug(f"Stored in S3: {key}")

        except Exception as e:
            logger.error(f"S3 storage failed: {e}")
            # Don't fail the whole learning process if S3 fails

    async def _should_retrain(self) -> bool:
        """
        Check if enough experiences collected for retraining.

        Threshold: 10,000 experiences from last 7 days.
        """
        try:
            from datetime import timedelta

            today = datetime.utcnow().date()
            count = 0

            for i in range(7):
                date = today - timedelta(days=i)
                prefix = f"experiences/{date}/"

                try:
                    response = self.s3.list_objects_v2(
                        Bucket=self.ml_bucket,
                        Prefix=prefix
                    )
                    count += response.get("KeyCount", 0)
                except:
                    pass

            threshold = 10000
            return count >= threshold

        except Exception as e:
            logger.error(f"Retraining check failed: {e}")
            return False

    async def _trigger_retraining(self):
        """Trigger SageMaker pipeline for model retraining."""
        try:
            response = self.sagemaker.start_pipeline_execution(
                PipelineName=self.pipeline_name,
                PipelineParameters=[
                    {
                        "Name": "TrainingDate",
                        "Value": datetime.utcnow().isoformat()
                    }
                ]
            )

            logger.info(
                f"Model retraining triggered: "
                f"{response['PipelineExecutionArn']}"
            )

        except Exception as e:
            logger.error(f"Retraining trigger failed: {e}")
            # Don't fail the learning process if SageMaker trigger fails


# Singleton
_learner = None


def get_async_learner() -> AsyncLearnerAgent:
    """Get singleton async learner instance."""
    global _learner
    if _learner is None:
        _learner = AsyncLearnerAgent()
    return _learner
