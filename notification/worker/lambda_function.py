import json
import os
import logging

import boto3

from botocore.exceptions import ClientError

from shared.models import NotificationPayload
from templates import ALERT_BODY_HTML, ALERT_BODY_TEXT, ALERT_SUBJECT

# Init Logger
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Init SES client
ses_client = boto3.client("ses", region_name="ap-southeast-1")

# Read env variables
SENDER_EMAIL = os.environ.get("SENDER_EMAIL")


def _send_email(payload: NotificationPayload):
    """
    Formats and sends the email using Amazon SES.
    """

    subject = ALERT_SUBJECT.format(
        risk_level=payload.risk_level,
        planning_area=payload.planning_area,
    )

    body_text = ALERT_BODY_TEXT.format(
        risk_level=payload.risk_level,
        planning_area=payload.planning_area,
    )

    body_html = ALERT_BODY_HTML.format(
        risk_level=payload.risk_level,
        planning_area=payload.planning_area,
    )

    try:
        response = ses_client.send_email(
            Source=SENDER_EMAIL,
            Destination={"ToAddresses": [payload.email]},
            Message={
                "Subject": {"Data": subject},
                "Body": {"Text": {"Data": body_text}, "Html": {"Data": body_html}},
            },
        )

        logger.info(
            f"Email sent successfully to {payload.email}. SES Message ID: {response['MessageId']}"
        )

    except ClientError as e:
        logger.error(f"SES Error sending to {payload.email}: {e.response['Error']['Message']}")
        raise e


def lambda_handler(event, context):
    """
    Triggered by SQS. Handles a batch of up to 10 messages.
    """

    batch_item_failures = []

    for record in event.get("Records", []):
        message_id = record["messageId"]

        try:
            body_dict = json.loads(record["body"])
            payload = NotificationPayload(**body_dict)

            logger.info(f"Sending alert for {payload.email} in {payload.planning_area}")

            _send_email(payload)

        except Exception as e:
            logger.error(f"Failed to process message {message_id}: {str(e)}")
            batch_item_failures.append({"itemIdentifier": message_id})

    return {"batchItemFailures": batch_item_failures}
