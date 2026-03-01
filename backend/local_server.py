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
from flask import Flask, request, Response

from risk_map.handler import handler as risk_map_handler
from subscriptions.handler import handler as subscriptions_handler

app = Flask(__name__)


def _lambda_event(method: str, path: str, body: str | None = None) -> dict:
    return {
        "httpMethod": method,
        "path": path,
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
    return _flask_response(risk_map_handler(_lambda_event("GET", "/risk-map"), None))


@app.route("/postal-code/<postal_code>", methods=["GET"])
def postal_code(postal_code: str):
    return _flask_response(
        risk_map_handler(_lambda_event("GET", f"/postal-code/{postal_code}"), None)
    )


@app.route("/subscriptions", methods=["GET", "POST"])
def subscriptions():
    body = request.get_data(as_text=True) or None
    return _flask_response(
        subscriptions_handler(_lambda_event(request.method, "/subscriptions", body), None)
    )


if __name__ == "__main__":
    debug_mode = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=8000, debug=debug_mode)
