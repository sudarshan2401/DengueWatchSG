"""
OneMap Token Refresher Lambda
------------------------------
Fetches a fresh OneMap token using stored credentials and writes it to SSM.
Triggered by EventBridge every 2 days.
"""
import json
import logging
import os
import urllib.request
import urllib.error
import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

ONEMAP_AUTH_URL   = "https://www.onemap.gov.sg/api/auth/post/getToken"
SSM_EMAIL_PATH    = "/denguewatch/onemap/email"
SSM_PASSWORD_PATH = "/denguewatch/onemap/password"
SSM_TOKEN_PATH    = "/denguewatch/onemap/token"


def lambda_handler(event, context):
    ssm = boto3.client("ssm", region_name=os.environ.get("AWS_REGION", "ap-southeast-1"))

    # Step 1: read credentials from SSM
    email    = ssm.get_parameter(Name=SSM_EMAIL_PATH,    WithDecryption=True)["Parameter"]["Value"]
    password = ssm.get_parameter(Name=SSM_PASSWORD_PATH, WithDecryption=True)["Parameter"]["Value"]

    # Step 2: call OneMap auth API
    payload = json.dumps({"email": email, "password": password}).encode()
    req = urllib.request.Request(
        ONEMAP_AUTH_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        logger.error(f"OneMap auth failed: {e.code} {e.reason} — {e.read().decode()}")
        raise

    token = data.get("access_token")
    if not token:
        raise ValueError(f"No access_token in OneMap response: {data}")

    # Step 3: write fresh token back to SSM
    ssm.put_parameter(Name=SSM_TOKEN_PATH, Value=token, Type="SecureString", Overwrite=True)
    logger.info("OneMap token refreshed successfully")
    return {"status": "ok"}
