"""
Data Ingestion ETL Lambda (Dengue Cluster)
-------------------------------------------
Pulls dengue cluster from the data.gov.sg API,
cleans the data and uploads into the S3 bucket.

Scheduled weekly via Amazon EventBridge.
"""

import json
import boto3
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

s3 = boto3.client("s3")
BUCKET_NAME = "dengue-ml-data-lake"

DENGUE_API_POLL = "https://api-open.data.gov.sg/v1/public/api/datasets/d_dbfabf16158d1b0e1c420627c0819168/poll-download"

def fetch_api(url):
    default_headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    req = urllib.request.Request(url, headers=default_headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return json.loads(response.read())
    except Exception as e:
        print(f"API request failed: {e}")
        return None

def upload_to_s3(key, data):
    s3.put_object(
        Bucket=BUCKET_NAME,
        Key=key,
        Body=json.dumps(data),
        ContentType="application/json"
    )

def clean_dengue_data(api_response, ingested_at):
    cleaned = []
    features = api_response.get("features", [])
    for f in features:
        props = f.get("properties", {})
        cleaned.append({
            "object_id": props.get("OBJECTID"),
            "locality": props.get("LOCALITY"),
            "case_size": props.get("CASE_SIZE"),
            "hyperlink": props.get("HYPERLINK"),
            "geometry": f.get("geometry"),
            "ingested_at": ingested_at
        })
    return cleaned

def lambda_handler(event, context):
    now = datetime.now(ZoneInfo("Asia/Singapore"))
    timestamp = now.isoformat()
    date_str = now.strftime("%Y-%m-%d")

    poll_response = fetch_api(DENGUE_API_POLL)
    if not poll_response or poll_response.get("code") != 0:
        print("Failed to poll dengue dataset")
        return {"statusCode": 500, "body": "Dengue poll failed"}

    dataset_url = poll_response["data"]["url"]
    data = fetch_api(dataset_url)
    if not data:
        print("Failed to download dengue dataset")
        return {"statusCode": 500, "body": "Dengue download failed"}

    cleaned = clean_dengue_data(data, timestamp)
    if cleaned:
        s3_key = f"raw/dengue/date={date_str}/clusters.json"
        upload_to_s3(s3_key, cleaned)
        print("Uploaded dengue clusters")

    return {"statusCode": 200, "body": "Dengue ingestion completed"}