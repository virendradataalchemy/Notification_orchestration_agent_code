"""Learning tools using ChromaDB and S3 storage."""
from strands.tools import tool
from typing import Dict, Any
from datetime import datetime, timedelta
from src.agents.memory import get_agent_memory
from src.services.embedding_service import EmbeddingService
import boto3
import json
import os
import logging

logger = logging.getLogger(__name__)


@tool
async def record_decision_in_memory(
    notification_id: str,
    user_id: str,
    state: Dict[str, Any],
    action: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Record agent decision in ChromaDB for future learning.

    Stores decision for future similarity searches.

    Args:
        notification_id: The notification identifier
        user_id: The user's ID
        state: State when decision was made
        action: Action taken (channel, timing)

    Returns:
        Confirmation of storage
    """
    try:
        # Create decision text
        decision_text = f"""
User: {user_id}
Type: {state.get('notification_type', 'unknown')}
Priority: {state.get('priority', 'medium')}
Channel Selected: {action.get('channel', 'email')}
Reasoning: {action.get('reasoning', 'N/A')}
Timestamp: {datetime.utcnow().isoformat()}
        """.strip()

        # Generate embedding
        embeddings = EmbeddingService()
        embedding = embeddings.generate_embedding(decision_text)

        # Store in ChromaDB
        memory = get_agent_memory()
        memory.store_decision(
            notification_id=notification_id,
            decision_text=decision_text,
            embedding=embedding,
            metadata={
                "user_id": user_id,
                "channel": action.get("channel"),
                "priority": state.get("priority"),
                "notification_type": state.get("notification_type"),
                "timestamp": datetime.utcnow().isoformat(),
                "outcome_recorded": False
            }
        )

        return {
            "stored": True,
            "notification_id": notification_id,
            "storage": "chromadb"
        }
    except Exception as e:
        logger.error(f"Failed to record decision in memory: {e}")
        return {
            "stored": False,
            "error": str(e)
        }


@tool
async def record_outcome_in_s3(
    notification_id: str,
    user_id: str,
    channel: str,
    notification_type: str,
    priority: str,
    outcome: Dict[str, Any],
    reward: float
) -> Dict[str, Any]:
    """
    Record outcome in S3 for ML model retraining.

    Stores experience data for future SageMaker training.

    Args:
        notification_id: The notification identifier
        user_id: The user's ID
        channel: Channel used
        notification_type: Type of notification
        priority: Priority level
        outcome: Outcome data (delivered, opened, clicked, failed)
        reward: Calculated reward

    Returns:
        Confirmation of S3 storage
    """
    try:
        s3 = boto3.client('s3')
        bucket = os.getenv("ML_BUCKET", "notification-ml-data")

        experience_data = {
            "notification_id": notification_id,
            "user_id": user_id,
            "channel": channel,
            "notification_type": notification_type,
            "priority": priority,
            "outcome": outcome,
            "reward": reward,
            "timestamp": datetime.utcnow().isoformat()
        }

        # Store in S3
        key = f"experiences/{datetime.utcnow().date()}/{notification_id}.json"

        s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=json.dumps(experience_data)
        )

        logger.debug(f"Stored experience in S3: {key}")

        return {
            "stored": True,
            "s3_key": key,
            "bucket": bucket
        }
    except Exception as e:
        logger.error(f"Failed to store in S3: {e}")
        return {
            "stored": False,
            "error": str(e)
        }


@tool
async def check_retraining_threshold() -> Dict[str, Any]:
    """
    Check if enough experiences collected for model retraining.

    Counts experiences from S3 for last 7 days.

    Returns:
        Whether retraining should be triggered and experience count
    """
    try:
        s3 = boto3.client('s3')
        bucket = os.getenv("ML_BUCKET", "notification-ml-data")

        # Count experiences from last 7 days
        today = datetime.utcnow().date()
        count = 0

        for i in range(7):
            date = today - timedelta(days=i)
            prefix = f"experiences/{date}/"

            try:
                response = s3.list_objects_v2(
                    Bucket=bucket,
                    Prefix=prefix
                )
                count += response.get("KeyCount", 0)
            except:
                pass

        threshold = 10000
        should_retrain = count >= threshold

        return {
            "experience_count": count,
            "threshold": threshold,
            "should_retrain": should_retrain,
            "reason": f"Collected {count} experiences, threshold is {threshold}"
        }
    except Exception as e:
        logger.error(f"Failed to check retraining threshold: {e}")
        return {
            "experience_count": 0,
            "threshold": 10000,
            "should_retrain": False,
            "error": str(e)
        }


@tool
async def trigger_model_retraining() -> Dict[str, Any]:
    """
    Trigger SageMaker pipeline for model retraining.

    Starts the ML retraining pipeline when threshold is reached.

    Returns:
        Confirmation of pipeline execution
    """
    try:
        sagemaker = boto3.client('sagemaker')
        pipeline_name = os.getenv("SAGEMAKER_PIPELINE", "notification-ml-retraining")

        response = sagemaker.start_pipeline_execution(
            PipelineName=pipeline_name,
            PipelineParameters=[
                {
                    "Name": "TrainingDate",
                    "Value": datetime.utcnow().isoformat()
                }
            ]
        )

        logger.info(f"Model retraining triggered: {response['PipelineExecutionArn']}")

        return {
            "triggered": True,
            "pipeline_execution_arn": response["PipelineExecutionArn"],
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Failed to trigger retraining: {e}")
        return {
            "triggered": False,
            "error": str(e)
        }
