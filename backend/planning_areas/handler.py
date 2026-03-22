"""
Planning Areas Lambda Handler
------------------------------
GET /planning-areas → GeoJSON FeatureCollection of Singapore planning area boundaries
"""
import json
import os
import logging
import urllib.request
import urllib.error
import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

ONEMAP_ALL_PLANNING_AREA_URL = "https://www.onemap.gov.sg/api/public/popapi/getAllPlanningarea"
SSM_TOKEN_PATH = "/denguewatch/onemap/token"

ONEMAP_REFRESHER_FUNCTION = "OneMapTokenRefresher"

_cached_token = None


def _get_token() -> str:
    global _cached_token
    if os.environ.get("ONEMAP_TOKEN"):
        return os.environ["ONEMAP_TOKEN"]
    if _cached_token:
        return _cached_token
    ssm = boto3.client("ssm", region_name=os.environ.get("AWS_REGION", "ap-southeast-1"))
    _cached_token = ssm.get_parameter(Name=SSM_TOKEN_PATH, WithDecryption=True)["Parameter"]["Value"]
    return _cached_token


def _refresh_token() -> str:
    global _cached_token
    logger.info("Token expired (401) — invoking OneMapTokenRefresher")
    boto3.client("lambda", region_name=os.environ.get("AWS_REGION", "ap-southeast-1")).invoke(
        FunctionName=ONEMAP_REFRESHER_FUNCTION,
        InvocationType="RequestResponse",
    )
    _cached_token = None
    return _get_token()


def _fetch_planning_areas(_retried: bool = False):
    token = _get_token()
    req = urllib.request.Request(
        f"{ONEMAP_ALL_PLANNING_AREA_URL}?year=2019",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 401 and not _retried:
            _refresh_token()
            return _fetch_planning_areas(_retried=True)
        raise


def lambda_handler(event, context):
    method = (event.get("requestContext") or {}).get("http", {}).get("method", "GET")
    if method == "OPTIONS":
        return _respond(200, {})

    try:
        raw = _fetch_planning_areas()
    except urllib.error.HTTPError as e:
        logger.error(f"OneMap getAllPlanningarea failed: {e.code} {e.reason}")
        return _respond(502, {"error": "Failed to fetch planning areas from OneMap"})
    except Exception as e:
        logger.error(f"Unhandled error: {e}")
        return _respond(500, {"error": "Internal server error"})

    # OneMap returns either a bare list or {"SearchResults": [...]}
    results = raw if isinstance(raw, list) else raw.get("SearchResults", [])

    features = []
    for area in results:
        name = area.get("pln_area_n", "")
        geojson_str = area.get("geojson", "")
        if not name or not geojson_str:
            continue
        try:
            geometry = json.loads(geojson_str)
        except (json.JSONDecodeError, TypeError):
            logger.warning(f"Could not parse geojson for {name}")
            continue
        features.append({
            "type": "Feature",
            "properties": {"name": name},
            "geometry": geometry,
        })

    logger.info(f"Returning {len(features)} planning area features")
    return _respond(200, {"type": "FeatureCollection", "features": features})


def _respond(status, body):
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "https://d88203gxr9nw1.cloudfront.net",
            "Access-Control-Allow-Headers": "Content-Type",
            "Access-Control-Allow-Methods": "GET,OPTIONS",
        },
        "body": json.dumps(body),
    }
