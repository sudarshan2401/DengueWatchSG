"""
Risk Map Ingestion Worker
-------------------------
Triggered by: S3 (s3:ObjectCreated:*)
Action: Reads JSON from S3, parses into Dataclasses, and upserts into RDS.
"""

import json
import os
import logging
import urllib.parse
from dataclasses import dataclass

import boto3
import psycopg2
import psycopg2.extras

# Init Logger
logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3_client = boto3.client("s3")
_conn = None

# Environment variables
DB_HOST = os.environ["DB_HOST"]
DB_NAME = os.environ["DB_NAME"]
DB_USER = os.environ["DB_USER"]
DB_PASSWORD = os.environ["DB_PASSWORD"]


@dataclass
class PredictionRecord:
    planning_area: str
    risk_level: str
    score: float

    def __post_init__(self):
        """Strict runtime type casting."""
        self.score = float(self.score)


def _get_conn():
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


def _fetch_and_parse_json(bucket_name: str, object_key: str) -> tuple[list[PredictionRecord], str]:
    """
    Downloads the JSON payload from S3, validates the schema,
    and returns a list of PredictionRecord dataclasses along with the week string.
    """
    try:
        response = s3_client.get_object(Bucket=bucket_name, Key=object_key)
        raw_content = response["Body"].read().decode("utf-8")
        json_data = json.loads(raw_content)

        # Extract the week from the root payload
        week_str = json_data.get("week")
        if not week_str:
            raise ValueError("JSON payload is missing the 'week' field.")

        records = []
        predictions = json_data.get("predictions", [])

        # Validate and append PredictionRecords
        for row in predictions:
            valid_record = PredictionRecord(**row)
            records.append(valid_record)

        logger.info(f"Successfully validated and parsed {len(records)} objects for week {week_str}")
        return records, week_str

    except Exception as e:
        logger.error(f"Failed to read/parse S3 object {object_key}: {e}")
        raise e


def _upsert_risk_data(records: list[PredictionRecord], week_str: str):
    """Formats Dataclasses into tuples and executes a batch UPSERT into PostgreSQL."""
    conn = _get_conn()
    cur = conn.cursor()

    # Flatten the dataclasses into the tuples required by psycopg2
    records_to_insert = [
        (
            r.planning_area.strip(),
            r.risk_level.strip(),
            r.score,
            week_str,
        )
        for r in records
    ]

    try:
        insert_query = """
            INSERT INTO planning_area_risk (planning_area, risk_level, score, week)
            VALUES %s
            ON CONFLICT (planning_area, week)
            DO UPDATE SET 
                risk_level = EXCLUDED.risk_level,
                score = EXCLUDED.score;
        """
        psycopg2.extras.execute_values(cur, insert_query, records_to_insert, page_size=100)
        conn.commit()
        logger.info(f"Results for week {week_str} upserted successfully.")

    except Exception as e:
        conn.rollback()
        logger.error(f"Failed to upsert results for week {week_str}: {e}")
        raise e
    finally:
        cur.close()


def lambda_handler(event, context):
    """Entry point for the S3 trigger."""
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
        # Fetch, Validate, and Parse
        records, week_str = _fetch_and_parse_json(bucket_name, object_key)

        # Upsert to RDS
        if records:
            _upsert_risk_data(records, week_str)
        else:
            logger.info("Predictions array was empty. Nothing to insert.")

    except Exception as e:
        return {"statusCode": 500, "body": "Internal processing error"}

    return {"statusCode": 200, "body": "Ingestion successful"}
