"""
Subscriptions Lambda Handler
-----------------------------
POST /subscriptions  → create or update an email subscription with postal codes
GET  /subscriptions  → (admin) list all subscriptions
"""
from __future__ import annotations

import json
import os
import logging
import psycopg2
from psycopg2.extras import RealDictCursor

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def _get_db_connection():
    return psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=int(os.environ.get("DB_PORT", 5432)),
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
    )


def _response(status_code: int, body: object) -> dict:
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body),
    }


def handler(event: dict, context) -> dict:  # noqa: ANN001
    http_method = event.get("httpMethod", "POST")

    try:
        conn = _get_db_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if http_method == "POST":
                return _handle_subscribe(cur, conn, event)
            elif http_method == "GET":
                return _handle_list(cur)
            else:
                return _response(405, {"error": "Method not allowed"})
    except Exception as exc:
        logger.exception("Unhandled error: %s", exc)
        return _response(500, {"error": "Internal server error"})
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _handle_subscribe(cur, conn, event: dict) -> dict:
    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return _response(400, {"error": "Invalid JSON body"})

    email: str = body.get("email", "").strip().lower()
    postal_codes: list[str] = body.get("postalCodes", [])

    if not email or "@" not in email:
        return _response(400, {"error": "Invalid email address"})
    if not postal_codes or not isinstance(postal_codes, list):
        return _response(400, {"error": "postalCodes must be a non-empty list"})

    invalid = [c for c in postal_codes if not (isinstance(c, str) and c.isdigit() and len(c) == 6)]
    if invalid:
        return _response(400, {"error": f"Invalid postal codes: {invalid}"})

    # Upsert subscription
    cur.execute(
        """
        INSERT INTO subscriptions (email, postal_codes)
        VALUES (%s, %s)
        ON CONFLICT (email)
        DO UPDATE SET postal_codes = EXCLUDED.postal_codes, updated_at = NOW()
        """,
        (email, postal_codes),
    )
    conn.commit()
    logger.info("Subscription upserted for %s", email)
    return _response(201, {"message": "Subscription saved", "email": email})


def _handle_list(cur) -> dict:
    cur.execute("SELECT email, postal_codes, created_at FROM subscriptions ORDER BY created_at DESC")
    rows = cur.fetchall()
    result = [
        {
            "email": row["email"],
            "postalCodes": row["postal_codes"],
            "createdAt": row["created_at"].isoformat() if row["created_at"] else None,
        }
        for row in rows
    ]
    return _response(200, result)
