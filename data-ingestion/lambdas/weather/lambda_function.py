"""
Data Ingestion ETL Lambda (Weather Data)
-------------------------------------------
Pulls rainfall and air temperature data from the data.gov.sg API,
cleans the data and uploads into the S3 bucket.

Scheduled weekly via Amazon EventBridge.

Environment Variables:
- API_KEY: API key for accessing the NEA data.gov.sg API stored in Lambda environment variables.

"""

import json
import boto3
import urllib.request
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

s3 = boto3.client("s3")
BUCKET_NAME = "dengue-ml-data-lake"

API_URLS = {
    "rainfall": "https://api-open.data.gov.sg/v2/real-time/api/rainfall",
    "air-temperature": "https://api-open.data.gov.sg/v2/real-time/api/air-temperature"
}

HEADERS = {"X-Api-Key": os.environ.get("API_KEY", "")}

def fetch_api(url, headers=None):
    default_headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    if headers:
        default_headers.update(headers)
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

def clean_weather_data(api_response, metric, ingested_at):
    cleaned = []
    readings_list = api_response.get("data", {}).get("readings", [])
    for item in readings_list:
        timestamp = item.get("timestamp")
        for r in item.get("data", []):
            cleaned.append({
                "station_id": r.get("stationId"),
                "metric": metric,
                "value": r.get("value"),
                "reading_timestamp": timestamp,
                "ingested_at": ingested_at
            })
    return cleaned

def lambda_handler(event, context):
    now = datetime.now(ZoneInfo("Asia/Singapore"))
    timestamp = now.isoformat()

    ## To get the previous days weather reports
    yesterday = now - timedelta(days=1)
    yest_date_str = yesterday.strftime("%Y-%m-%d")

    for metric, url in API_URLS.items():
        api_url = f"{url}?date={yest_date_str}"
        data = fetch_api(api_url, headers=HEADERS)
        if not data:
            print(f"No weather data for {metric}")
            continue

        cleaned = clean_weather_data(data, metric, timestamp)
        if cleaned:
            s3_key = f"raw/weather/date={yest_date_str}/{metric}.json"
            upload_to_s3(s3_key, cleaned)
            print(f"Uploaded {metric} data")

    return {"statusCode": 200, "body": "Weather ingestion completed"}