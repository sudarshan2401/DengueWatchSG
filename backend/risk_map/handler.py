"""
Risk Map Lambda Handler
-----------------------
GET /risk-map           → returns current weekly risk scores for all planning areas
GET /postal-code/{code} → returns planning area & risk level for a postal code
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
    path = event.get("path", "")
    http_method = event.get("httpMethod", "GET")

    if http_method != "GET":
        return _response(405, {"error": "Method not allowed"})

    try:
        conn = _get_db_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if path == "/risk-map":
                return _handle_risk_map(cur)
            elif path.startswith("/postal-code/"):
                postal_code = path.split("/postal-code/", 1)[1]
                return _handle_postal_code(cur, postal_code)
            else:
                return _response(404, {"error": "Not found"})
    except Exception as exc:
        logger.exception("Unhandled error: %s", exc)
        return _response(500, {"error": "Internal server error"})
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _handle_risk_map(cur) -> dict:  # noqa: ANN001
    cur.execute(
        """
        SELECT planning_area, risk_level, score, week
        FROM planning_area_risk
        WHERE week = (SELECT MAX(week) FROM planning_area_risk)
        ORDER BY planning_area
        """
    )
    rows = cur.fetchall()
    result = [
        {
            "planningArea": row["planning_area"],
            "riskLevel": row["risk_level"],
            "score": float(row["score"]),
            "week": row["week"],
        }
        for row in rows
    ]
    return _response(200, result)


def _handle_postal_code(cur, postal_code: str) -> dict:
    if not postal_code.isdigit() or len(postal_code) != 6:
        return _response(400, {"error": "Invalid postal code"})

    cur.execute(
        """
        SELECT pc.postal_code, pc.planning_area, r.risk_level
        FROM postal_code_mapping pc
        JOIN planning_area_risk r ON r.planning_area = pc.planning_area
        WHERE pc.postal_code = %s
          AND r.week = (SELECT MAX(week) FROM planning_area_risk)
        """,
        (postal_code,),
    )
    row = cur.fetchone()
    if row is None:
        return _response(404, {"error": "Postal code not found"})

    return _response(
        200,
        {
            "postalCode": row["postal_code"],
            "planningArea": row["planning_area"],
            "riskLevel": row["risk_level"],
        },
    )
