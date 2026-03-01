"""
Data Ingestion ETL Lambda
--------------------------
Pulls dengue cluster and weather data from the NEA data.gov.sg API
and upserts into the RDS PostgreSQL database.

Scheduled daily via Amazon EventBridge.

Environment Variables
---------------------
  DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD
  NEA_API_KEY   : API key for data.gov.sg
"""
from __future__ import annotations

import os
import logging
import datetime
import requests
import psycopg2

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

NEA_BASE_URL = "https://api.data.gov.sg/v1"
NEA_DENGUE_ENDPOINT = f"{NEA_BASE_URL}/environment/dengue-clusters"
NEA_RAINFALL_ENDPOINT = f"{NEA_BASE_URL}/environment/rainfall"
NEA_TEMPERATURE_ENDPOINT = f"{NEA_BASE_URL}/environment/air-temperature"


def _get_db_connection():
    return psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=int(os.environ.get("DB_PORT", 5432)),
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
    )


def _fetch_json(url: str, params: dict | None = None) -> dict:
    api_key = os.environ.get("NEA_API_KEY", "")
    headers = {"api-key": api_key} if api_key else {}
    resp = requests.get(url, params=params, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()


def fetch_dengue_clusters() -> list[dict]:
    """Fetch active dengue clusters from NEA API."""
    data = _fetch_json(NEA_DENGUE_ENDPOINT)
    features = data.get("features", [])
    clusters = []
    for feat in features:
        props = feat.get("properties", {})
        clusters.append(
            {
                "case_size": int(props.get("CASE_SIZE", 0)),
                "hyperlink": props.get("HYPERLINK", ""),
                "geometry": feat.get("geometry"),
            }
        )
    logger.info("Fetched %d dengue clusters", len(clusters))
    return clusters


def fetch_weather(endpoint: str, date_str: str) -> list[dict]:
    """Fetch weather readings for a given date."""
    data = _fetch_json(endpoint, params={"date": date_str})
    items = data.get("items", [])
    readings = []
    for item in items:
        for station_reading in item.get("readings", []):
            readings.append(
                {
                    "station_id": station_reading.get("station_id"),
                    "value": station_reading.get("value"),
                    "timestamp": item.get("timestamp"),
                }
            )
    return readings


def upsert_raw_dengue(conn, clusters: list[dict], ingested_at: str) -> None:
    with conn.cursor() as cur:
        for cluster in clusters:
            cur.execute(
                """
                INSERT INTO raw_dengue_clusters (case_size, hyperlink, geometry, ingested_at)
                VALUES (%s, %s, %s::jsonb, %s)
                """,
                (
                    cluster["case_size"],
                    cluster["hyperlink"],
                    str(cluster["geometry"]) if cluster["geometry"] else None,
                    ingested_at,
                ),
            )
    conn.commit()
    logger.info("Upserted %d dengue cluster rows", len(clusters))


def upsert_raw_weather(conn, readings: list[dict], metric: str, ingested_at: str) -> None:
    with conn.cursor() as cur:
        for r in readings:
            cur.execute(
                """
                INSERT INTO raw_weather (station_id, metric, value, reading_timestamp, ingested_at)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
                """,
                (r["station_id"], metric, r["value"], r["timestamp"], ingested_at),
            )
    conn.commit()
    logger.info("Upserted %d %s readings", len(readings), metric)


def handler(event: dict, context) -> dict:  # noqa: ANN001
    today = datetime.date.today().isoformat()
    ingested_at = datetime.datetime.utcnow().isoformat()

    try:
        conn = _get_db_connection()

        # Dengue clusters
        clusters = fetch_dengue_clusters()
        upsert_raw_dengue(conn, clusters, ingested_at)

        # Rainfall
        rainfall = fetch_weather(NEA_RAINFALL_ENDPOINT, today)
        upsert_raw_weather(conn, rainfall, "rainfall", ingested_at)

        # Temperature
        temperature = fetch_weather(NEA_TEMPERATURE_ENDPOINT, today)
        upsert_raw_weather(conn, temperature, "temperature", ingested_at)

        conn.close()
        logger.info("Data ingestion complete for %s", today)
        return {"statusCode": 200, "body": f"Ingestion complete for {today}"}

    except Exception as exc:
        logger.exception("Data ingestion failed: %s", exc)
        raise
