import boto3
import json
import uuid
import os
import logging
from dataclasses import asdict
from typing import List, Dict, Set, Any
from shared.models import NotificationPayload

# Init Logger
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Init SQS client
sqs = boto3.client("sqs", region_name="ap-southeast-1")

# Read env variables
QUEUE_URL = os.environ.get("SQS_QUEUE_URL", "")
DUMMY_EMAIL = os.environ.get("DUMMY_EMAIL", "")


def _get_high_risk_areas(predictions: Dict[str, str]) -> Set[str]:
    """Extracts a set of planning areas marked as 'High' risk."""
    return {area for area, risk in predictions.items() if risk == "High"}


def _get_affected_users(
    subscriptions: List[Dict[str, str]], high_risk_areas: Set[str]
) -> List[NotificationPayload]:
    """Filters subscriptions and returns affected user data."""
    affected_users: List[NotificationPayload] = []

    for sub in subscriptions:
        planning_area = sub["planning_area"]

        if planning_area in high_risk_areas:
            payload = NotificationPayload(
                email=sub["email"], planning_area=planning_area, risk_level="High"
            )
            affected_users.append(payload)

    return affected_users


def _push_to_sqs_in_batches(affected_users: List[NotificationPayload], batch_size: int = 10) -> None:
    """Chunks typed payload objects and pushes them to SQS in batches."""
    for i in range(0, len(affected_users), batch_size):
        batch = affected_users[i : i + batch_size]

        entries: List[Dict[str, str]] = []
        for user in batch:
            entries.append({"Id": str(uuid.uuid4()), "MessageBody": json.dumps(asdict(user))})

        try:
            if QUEUE_URL:
                sqs.send_message_batch(QueueUrl=QUEUE_URL, Entries=entries)
                logger.info(f"Successfully pushed batch of {len(batch)} messages to SQS.")
            else:
                logger.warning("SQS_QUEUE_URL not set. Skipping SQS push.")
        except Exception as e:
            logger.error(f"SQS push error for batch starting at index {i}: {str(e)}")


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    # TODO: Replace dummy data with actual data from SageMaker and DynamoDB
    predictions: Dict[str, str] = {"Bishan": "High", "Clementi": "Low", "Bukit Batok": "High"}
    subscriptions: List[Dict[str, str]] = [
        {"email": DUMMY_EMAIL, "planning_area": "Bishan"},
        {"email": DUMMY_EMAIL, "planning_area": "Clementi"},
        {"email": DUMMY_EMAIL, "planning_area": "Bukit Batok"},
    ]

    # Processing logic
    high_risk_areas: Set[str] = _get_high_risk_areas(predictions)
    logger.info(f"High risk areas: {high_risk_areas}")

    affected_users: List[NotificationPayload] = _get_affected_users(subscriptions, high_risk_areas)
    logger.info(f"Found {len(affected_users)} affected subscribers.")

    # Dispatch
    if affected_users:
        _push_to_sqs_in_batches(affected_users)

    return {
        "statusCode": 200,
        "body": json.dumps(f"Successfully triggered notification for {len(affected_users)} users."),
    }
