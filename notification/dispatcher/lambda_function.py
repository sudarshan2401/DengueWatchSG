import boto3
import json
import uuid
import os
import logging
import urllib.parse
import psycopg2
import psycopg2.extras
from dataclasses import asdict
from typing import List, Dict, Set, Any
from shared.models import NotificationPayload

# Init Logger
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Init Clients
sqs = boto3.client("sqs", region_name="ap-southeast-1")
s3_client = boto3.client("s3")

# Read env variables
QUEUE_URL = os.environ.get("SQS_QUEUE_URL")
DB_HOST = os.environ.get("DB_HOST")
DB_NAME = os.environ.get("DB_NAME")
DB_USER = os.environ.get("DB_USER")
DB_PASSWORD = os.environ.get("DB_PASSWORD")

_conn = None


def _get_conn():
    """Maintains a warm database connection."""
    global _conn
    if _conn is None or _conn.closed:
        _conn = psycopg2.connect(
            host=DB_HOST,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            connect_timeout=5,
        )
    return _conn


def _get_high_risk_areas(bucket_name: str, object_key: str) -> Set[str]:
    """Fetches predictions from S3 and extracts a set of 'High' risk planning areas."""
    try:
        response = s3_client.get_object(Bucket=bucket_name, Key=object_key)
        raw_content = response["Body"].read().decode("utf-8")
        json_data = json.loads(raw_content)

        predictions = json_data.get("predictions", [])

        # Build a set of areas where the risk level is High
        high_risk_areas = {
            row["planning_area"].strip()
            for row in predictions
            if row.get("risk_level", "").strip().lower() == "high"
        }

        logger.info(f"Extracted {len(high_risk_areas)} high-risk areas from S3.")
        return high_risk_areas

    except Exception as e:
        logger.error(f"Failed to fetch/parse S3 predictions from {object_key}: {e}")
        raise e


def _get_affected_users(high_risk_areas: Set[str]) -> List[NotificationPayload]:
    """Queries RDS for users subscribed to the identified high-risk areas."""
    if not high_risk_areas:
        return []

    affected_users: List[NotificationPayload] = []
    conn = _get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        # Check if planning_area matches any of the high risk areas
        query = "SELECT id, email, planning_area FROM subscriptions WHERE planning_area = ANY(%s::text[])"
        cur.execute(query, (list(high_risk_areas),))
        rows = cur.fetchall()

        for row in rows:
            payload = NotificationPayload(
                email=row["email"],
                planning_area=row["planning_area"].strip(),
                risk_level="High",
                subscription_id=str(row["id"])
            )
            affected_users.append(payload)

        logger.info(f"Generated {len(affected_users)} individual notification payloads.")
        return affected_users

    except Exception as e:
        logger.error(f"Failed to query RDS for affected users: {e}")
        raise e
    finally:
        cur.close()


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
    """Entry point triggered by S3 ObjectCreated."""
    try:
        sns_message = json.loads(event["Records"][0]["Sns"]["Message"])
        record = sns_message["Records"][0]
        bucket_name = record["s3"]["bucket"]["name"]
        object_key = urllib.parse.unquote_plus(record["s3"]["object"]["key"])

        logger.info(f"Processing new file: s3://{bucket_name}/{object_key}")
    except KeyError as e:
        logger.error(f"Invalid SNS event structure: {e}")
        return {"statusCode": 400, "body": "Invalid event"}

    try:
        # Parse high risk areas from the S3 JSON
        high_risk_areas: Set[str] = _get_high_risk_areas(bucket_name, object_key)

        if not high_risk_areas:
            logger.info("No high-risk areas identified. Skipping dispatch.")
            return {"statusCode": 200, "body": "No notifications required."}

        # Fetch affected users from PostgreSQL
        affected_users: List[NotificationPayload] = _get_affected_users(high_risk_areas)

        # Dispatch to SQS
        if affected_users:
            _push_to_sqs_in_batches(affected_users)
        else:
            logger.info("No users are subscribed to the current high-risk areas.")

    except Exception as e:
        return {"statusCode": 500, "body": "Internal server error"}

    return {
        "statusCode": 200,
        "body": json.dumps(f"Successfully triggered notification for {len(affected_users)} users."),
    }
