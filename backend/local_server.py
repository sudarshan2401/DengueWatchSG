"""
Local development server
------------------------
Wraps all Lambda handlers behind a simple Flask server so that the
frontend can talk to them without deploying to AWS.

Run with:
    python local_server.py
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from flask import Flask, request, Response

# Load .env if present (local dev only)
_env_file = Path(__file__).parent / ".env"
if _env_file.exists():
    for _line in _env_file.read_text().splitlines():
        if _line.strip() and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

from risk_map.handler import lambda_handler as risk_map_handler
from postal_code.handler import lambda_handler as postal_code_handler
from subscriptions.handler import lambda_handler as subscriptions_handler

app = Flask(__name__)


def _lambda_event(method: str, path: str, body: str | None = None) -> dict:
    return {
        "requestContext": {
            "http": {
                "method": method,
                "path": path,
            }
        },
        "body": body,
        "queryStringParameters": dict(request.args),
        "headers": dict(request.headers),
    }


def _flask_response(lambda_response: dict) -> Response:
    return Response(
        lambda_response["body"],
        status=lambda_response["statusCode"],
        headers=lambda_response.get("headers", {}),
    )


@app.route("/risk-map", methods=["GET"])
def risk_map():
    return _flask_response(risk_map_handler(_lambda_event("GET", "/default/dengue-api/risk"), None))


@app.route("/postal-code/<postal_code>", methods=["GET"])
def postal_code(postal_code: str):
    event = _lambda_event("GET", f"/postal-code/{postal_code}")
    event["pathParameters"] = {"code": postal_code}
    return _flask_response(postal_code_handler(event, None))


@app.route("/subscriptions", methods=["GET", "POST"])
def subscriptions():
    body = request.get_data(as_text=True) or None
    return _flask_response(
        subscriptions_handler(_lambda_event(request.method, "/default/dengue-api/subscribe", body), None)
    )


if __name__ == "__main__":
    debug_mode = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=8000, debug=debug_mode)
