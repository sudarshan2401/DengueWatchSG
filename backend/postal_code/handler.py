"""
Postal Code Lambda Handler
---------------------------
GET /postal-code/{code} → resolve a Singapore postal code to a planning area via OneMap API
"""
import json
import os
import logging
import urllib.request
import urllib.parse
import urllib.error
import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

ONEMAP_SEARCH_URL        = "https://www.onemap.gov.sg/api/common/elastic/search"
ONEMAP_PLANNING_AREA_URL = "https://www.onemap.gov.sg/api/public/popapi/getPlanningarea"
SSM_TOKEN_PATH           = "/denguewatch/onemap/token"

_cached_token = None  # cache the token in memory to avoid repeated SSM calls within the same Lambda instance


def _get_token() -> str:
    global _cached_token
    if os.environ.get("ONEMAP_TOKEN"):  # local dev fallback
        return os.environ["ONEMAP_TOKEN"]
    if _cached_token:
        return _cached_token
    ssm = boto3.client("ssm", region_name=os.environ.get("AWS_REGION", "ap-southeast-1"))
    _cached_token = ssm.get_parameter(Name=SSM_TOKEN_PATH, WithDecryption=True)["Parameter"]["Value"]
    return _cached_token


def lambda_handler(event, context):
    try:
        code = (event.get("pathParameters") or {}).get("code", "").strip()
        if not code:
            return _respond(400, {"error": "Postal code is required"})

        logger.info(f"Looking up planning area for postal code: {code}")
        planning_area = _lookup_planning_area(code)

        if not planning_area:
            return _respond(404, {"error": f"Could not resolve postal code {code} to a planning area"})

        planning_area_name, lat, lng = planning_area
        return _respond(200, {
            "postalCode": code,
            "planningArea": planning_area_name,
            "latitude": float(lat),
            "longitude": float(lng),
        })

    except Exception as e:
        logger.error(f"Unhandled error: {e}")
        return _respond(500, {"error": "Internal server error"})


def _lookup_planning_area(postal_code: str):
    token = _get_token()
    headers = {"Authorization": f"Bearer {token}"}

    # Step 1: get lat/lng from postal code
    params = urllib.parse.urlencode({
        "searchVal": postal_code,
        "returnGeom": "Y",
        "getAddrDetails": "N",
        "pageNum": "1",
    })
    req = urllib.request.Request(f"{ONEMAP_SEARCH_URL}?{params}", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            search_data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        logger.error(f"Step 1 (search) failed: {e.code} {e.reason} — body: {e.read().decode()}")
        raise

    results = search_data.get("results", [])
    if not results:
        logger.warning(f"No OneMap results for postal code: {postal_code}")
        return None

    lat = results[0].get("LATITUDE")
    lng = results[0].get("LONGITUDE")
    if not lat or not lng:
        return None

    logger.info(f"Step 1 ok: lat={lat!r}, lng={lng!r}")

    # Step 2: get planning area from lat/lng
    params = urllib.parse.urlencode({"latitude": lat, "longitude": lng})
    url = f"{ONEMAP_PLANNING_AREA_URL}?{params}"
    logger.info(f"Step 2 URL: {url}")
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            area_data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        logger.error(f"Step 2 (planning area) failed: {e.code} {e.reason} — body: {e.read().decode()}")
        raise

    if not area_data:
        logger.warning(f"No planning area returned for lat={lat}, lng={lng}")
        return None

    planning_area = area_data[0].get("pln_area_n", "")
    return (planning_area.upper(), lat, lng) if planning_area else None


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
