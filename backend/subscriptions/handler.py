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
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type",
            "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
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
                "id": 1,
                "email": "user@example.com",
                "planning_areas": ["area1", "area2"],
                "created_at": "2023-01-01T00:00:00",
                "updated_at": "2023-01-01T00:00:00"
            }
        ]
    }
    """
    conn = _get_conn()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("SELECT id, email, planning_areas, created_at, updated_at FROM subscriptions ORDER BY created_at DESC")
    rows = cur.fetchall()

    return _respond(200, {
        "subscriptions": [dict(row) for row in rows]
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
        cur.execute("SELECT id, planning_areas FROM subscriptions WHERE email = %s", (email,))
        existing = cur.fetchone()

        if existing:
            current_areas = existing["planning_areas"] or []
            new_areas = [a for a in planning_areas if a not in current_areas]

            if not new_areas:
                return _respond(409, {
                    "error": "Already subscribed to all given planning areas",
                    "subscribed_areas": current_areas
                })

            merged = current_areas + new_areas

            # updated_at set explicitly here instead of a trigger
            cur.execute("""
                UPDATE subscriptions
                SET    planning_areas = %s,
                       updated_at = NOW()
                WHERE  email = %s
                RETURNING id, email, planning_areas, updated_at
            """, (merged, email))

            row = cur.fetchone()
            conn.commit()
            
            logger.info(f"Updated subscription for {email}: added areas {new_areas}")

            return _respond(200, {
                "message":        "Subscription updated",
                "id":             row["id"],
                "email":          row["email"],
                "planning_areas": row["planning_areas"],
                "added_areas":    new_areas,
                "updated_at":     row["updated_at"].isoformat()
            })

        else:
            cur.execute("""
                INSERT INTO subscriptions (email, planning_areas)
                VALUES (%s, %s)
                RETURNING id, email, planning_areas, created_at
            """, (email, planning_areas))

            row = cur.fetchone()
            conn.commit()

            logger.info(f"Created new subscription for {email} with areas {planning_areas}")

            return _respond(201, {
                "message":        "Subscribed successfully",
                "id":             row["id"],
                "email":          row["email"],
                "planning_areas": row["planning_areas"],
                "created_at":     row["created_at"].isoformat()
            })

    except Exception as e:
        conn.rollback()
        logger.error(f"DB error: {e}")
        raise

    finally:
        cur.close()
