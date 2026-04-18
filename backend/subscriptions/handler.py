"""
Subscriptions Lambda Handler
-----------------------------
POST /subscriptions  → create or update an email subscription with postal codes
GET  /subscriptions  → (admin) list all subscriptions
"""
import json
import os
import logging
import psycopg2
import psycopg2.extras
from email_validator import validate_email, EmailNotValidError
from datetime import datetime
from decimal import Decimal
import boto3

_conn = None

logger = logging.getLogger()
logger.setLevel(logging.INFO)
ses_client = boto3.client("ses", region_name="ap-southeast-1")

def lambda_handler(event, context):
    method = event["requestContext"]["http"]["method"]
    path   = event["requestContext"]["http"]["path"]

    try:
        if method == "OPTIONS":
            return _respond(200, {})

        if method == "GET" and path == "/default/dengue-api/subscribe":
            return _get_subscriptions()

        if method == "POST" and path == "/default/dengue-api/subscribe":
            body = json.loads(event.get("body") or "{}")
            return _post_subscribe(body)
        
        if (method == "GET" and path == "/default/dengue-api/unsubscribe"):
            uuid = event.get('queryStringParameters', {}).get('uuid')
            if not uuid:
                return _respond(400, {"error": "uuid parameter required"})
            return _delete_subscription(uuid)

        return _respond(404, {"error": "Route not found"})

    except Exception as e:
        logger.error(f"Unhandled error: {e}")
        return _respond(500, {"error": "Internal server error"})

def _get_conn():
    global _conn
    if _conn is None or _conn.closed:
        _conn = psycopg2.connect(
            host=os.environ["DB_HOST"],
            dbname=os.environ["DB_NAME"],
            user=os.environ["DB_USER"],
            password=os.environ["DB_PASSWORD"],
            connect_timeout=5
        )
    return _conn

def _respond(status, body):
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "https://d88203gxr9nw1.cloudfront.net",
            "Access-Control-Allow-Headers": "Content-Type",
            "Access-Control-Allow-Methods": "GET,POST,OPTIONS,DELETE",
        },
        "body": json.dumps(body, default=json_serial)
    }

def json_serial(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Type {type(obj)} not serializable")

def _get_subscriptions():
    """
    List all subscriptions (admin use only)
    Response format:
    {
        "subscriptions": [
            {
                "id": "uuid",
                "email": "user@example.com",
                "planning_area": "area1",
                "created_at": "2023-01-01T00:00:00"
            }
        ]
    }
    """
    conn = _get_conn()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("SELECT id, email, planning_area, created_at FROM subscriptions")

    rows = cur.fetchall()

    return _respond(200, {
        "subscriptions": rows
    })


def _trigger_ses_verification(email):
    """
    Checks if an email is already verified. 
    Triggers a new verification email ONLY if the status is NOT Success or Pending.
    """
    try:
        # Check current verification status from AWS
        response = ses_client.get_identity_verification_attributes(Identities=[email])
        attributes = response.get('VerificationAttributes', {}).get(email, {})
        status = attributes.get('VerificationStatus')

        if status == 'Success':
            logger.info(f"User {email} is already verified. Skipping email.")
            return
        
        if status == 'Pending':
            logger.info(f"Verification for {email} is already in progress. Skipping.")
            return

        # Trigger verification for New, Failed, or NotFound identities
        ses_client.verify_email_identity(EmailAddress=email)
        logger.info(f"Verification email triggered for: {email}")

    except ClientError as e:
        logger.error(f"SES Error for {email}: {e.response['Error']['Message']}")

def _post_subscribe(body):
    """
    Create or update a subscription for the given email and planning areas.
    Expected body format:
    {
        "email": "user@example.com",
        "planning_areas": ["area1", "area2"]
    }
    """
    email          = (body.get("email") or "").strip().lower()
    planning_areas = body.get("planning_areas", [])

    # Validate email and planning areas
    if not email:
        return _respond(400, {"error": "email is required"})

    try:
        valid = validate_email(email, check_deliverability=False)
        email = valid.normalized  # returns cleaned canonical form
    except EmailNotValidError as e:
        return _respond(400, {"error": "Invalid email address"})

    # Trigger SES verification email
    _trigger_ses_verification(email)
    
    if not planning_areas or not isinstance(planning_areas, list):
        return _respond(400, {"error": "planning_areas must be a non-empty list"})

    planning_areas = list({a.strip() for a in planning_areas if isinstance(a, str) and a.strip()})

    if not planning_areas:
        return _respond(400, {"error": "planning_areas contains no valid entries"})

    logger.info(f"Processing subscription for email: {email}, planning areas: {planning_areas}")

    conn = _get_conn()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        for area in planning_areas:
            cur.execute("""
                INSERT INTO subscriptions (email, planning_area)
                VALUES (%s, %s)
                ON CONFLICT (email, planning_area) DO NOTHING
            """, (email, area))
        
        conn.commit()

        return _respond(200, {"message": "Subscription updated successfully"})

    except Exception as e:
        conn.rollback()
        logger.error(f"DB error: {e}")
        raise

    finally:
        cur.close()

def _delete_subscription(uuid):
    """
    Delete a subscription by UUID.
    """
    conn = _get_conn()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        cur.execute("SELECT email FROM subscriptions WHERE id = %s", (uuid,))
        existing = cur.fetchone()

        if not existing:
            return _respond(404, {"error": "Subscription not found"})

        email = existing["email"]

        cur.execute("DELETE FROM subscriptions WHERE id = %s", (uuid,))
        conn.commit()

        logger.info(f"Deleted subscription {uuid} for email {email}")

        return _respond(200, {"message": "Subscription deleted"})

    except Exception as e:
        conn.rollback()
        logger.error(f"DB error: {e}")
        raise

    finally:
        cur.close()
