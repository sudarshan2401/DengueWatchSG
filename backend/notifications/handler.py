"""
Notification Risk-Change Detector Lambda
-----------------------------------------
Triggered weekly (after SageMaker inference) via EventBridge.

Logic:
  1. Compare this week's risk scores with last week's for each planning area.
  2. For each area whose risk worsened (Low→Medium, Low→High, Medium→High),
     find all subscribed emails that monitor a postal code in that area.
  3. Push a message per (email, area) to SQS → SNS delivers the email.
"""
from __future__ import annotations

import json
import os
import logging
import boto3
import psycopg2
from psycopg2.extras import RealDictCursor

logger = logging.getLogger()
logger.setLevel(logging.INFO)

RISK_ORDER = {"Low": 0, "Medium": 1, "High": 2}


def _get_db_connection():
    return psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=int(os.environ.get("DB_PORT", 5432)),
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
    )


def handler(event: dict, context) -> dict:  # noqa: ANN001
    conn = _get_db_connection()
    sqs = boto3.client("sqs", region_name=os.environ.get("AWS_REGION", "ap-southeast-1"))
    queue_url = os.environ["SQS_QUEUE_URL"]

    messages_sent = 0
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Fetch the two most recent weeks
            cur.execute("SELECT DISTINCT week FROM planning_area_risk ORDER BY week DESC LIMIT 2")
            weeks = [row["week"] for row in cur.fetchall()]
            if len(weeks) < 2:
                logger.info("Not enough data to compare weeks; skipping.")
                return {"statusCode": 200, "body": "No comparison needed"}

            current_week, previous_week = weeks[0], weeks[1]

            # Detect worsened areas
            cur.execute(
                """
                SELECT cur.planning_area,
                       prev.risk_level AS prev_risk,
                       cur.risk_level  AS cur_risk
                FROM planning_area_risk cur
                JOIN planning_area_risk prev
                  ON cur.planning_area = prev.planning_area
                 AND prev.week = %s
                WHERE cur.week = %s
                """,
                (previous_week, current_week),
            )
            worsened = [
                row for row in cur.fetchall()
                if RISK_ORDER.get(row["cur_risk"], 0) > RISK_ORDER.get(row["prev_risk"], 0)
            ]

            if not worsened:
                logger.info("No worsened areas this week.")
                return {"statusCode": 200, "body": "No alerts to send"}

            for area_row in worsened:
                area = area_row["planning_area"]
                prev_risk = area_row["prev_risk"]
                cur_risk = area_row["cur_risk"]

                # Find subscribed emails for this area
                cur.execute(
                    """
                    SELECT DISTINCT s.email
                    FROM subscriptions s
                    JOIN postal_code_mapping pc ON pc.postal_code = ANY(s.postal_codes)
                    WHERE pc.planning_area = %s
                    """,
                    (area,),
                )
                emails = [row["email"] for row in cur.fetchall()]

                for email in emails:
                    message = {
                        "email": email,
                        "planningArea": area,
                        "previousRisk": prev_risk,
                        "currentRisk": cur_risk,
                        "week": current_week,
                    }
                    sqs.send_message(
                        QueueUrl=queue_url,
                        MessageBody=json.dumps(message),
                    )
                    messages_sent += 1
                    logger.info("Queued alert for %s → %s (%s→%s)", email, area, prev_risk, cur_risk)

    except Exception as exc:
        logger.exception("Error in notification handler: %s", exc)
        raise
    finally:
        conn.close()

    return {"statusCode": 200, "body": f"Queued {messages_sent} alert(s)"}
