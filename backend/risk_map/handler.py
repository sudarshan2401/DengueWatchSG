"""
Risk Map Lambda Handler
-----------------------
GET /risk         → returns current weekly risk scores for all planning areas
"""

import json
import os
import logging
import psycopg2
import psycopg2.extras

_conn = None

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    method = event["requestContext"]["http"]["method"]
    path   = event["requestContext"]["http"]["path"]

    try:
        if method == "GET" and path == "/default/dengue-api/risk":
            return get_latest_risk()
        
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
            "Access-Control-Allow-Methods": "GET,OPTIONS",
        },
        "body": json.dumps(body)
    }

# ── GET /risk ─────────────────────────────────────────────────────────────────

def get_latest_risk():
    conn = _get_conn()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""
        SELECT planning_area, risk_level, score, latitude, longitude, week
        FROM   planning_area_risk
        WHERE  week = (
            SELECT week FROM planning_area_risk
            ORDER  BY week DESC
            LIMIT  1
        )
        ORDER  BY planning_area
    """)

    rows = cur.fetchall()
    cur.close()

    if not rows:
        return _respond(404, {"error": "No risk data found"})
    
    logging.info(f"Fetched {len(rows)} risk records for week {rows[0]['week']}")

    return _respond(200, {
        "week": rows[0]["week"],
        "data": [
            {
                "planning_area": r["planning_area"],
                "risk_level":    r["risk_level"],
                "score":         float(r["score"]),
                "latitude":      float(r["latitude"]),
                "longitude":     float(r["longitude"])
            }
            for r in rows
        ]
    })
