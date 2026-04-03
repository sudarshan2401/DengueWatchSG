"""
DengueWatch SG — Batch Inference Script
-----------------------------------------
Reads feature CSV, runs the trained XGBoost model, and writes
prediction results as JSON to S3.

The downstream Lambda reads from S3 and loads predictions into RDS.

Usage (SageMaker Processing Job / standalone)
---------------------------------------------
    python inference.py \\
        --model-dir   ml/model \\
        --input-data  s3://dengue-ml-data-lake/features/week=2026-W12/features.csv \\
        --output      s3://dengue-ml-data-lake/predictions/week=2026-W12/results.json \\
        --week        2026-W12

Output JSON schema
------------------
    {
      "week": "2026-W12",
      "generated_at": "2026-03-17T00:00:00Z",
      "predictions": [
        {"planning_area": "GEYLANG", "risk_level": "High", "score": 0.82},
        ...
      ]
    }
"""
from __future__ import annotations

import argparse
import io
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import boto3
import joblib
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", default=os.environ.get("SM_MODEL_DIR", "model"))
    parser.add_argument("--input-data", required=True,
                        help="S3 URI or local path to features CSV")
    parser.add_argument("--output", required=True,
                        help="S3 URI or local path for predictions JSON")
    parser.add_argument("--week", required=True, help="ISO week string, e.g. 2026-W12")
    return parser.parse_args()


def load_features(input_path: str) -> pd.DataFrame:
    if input_path.startswith("s3://"):
        bucket, key = input_path[5:].split("/", 1)
        obj = boto3.client("s3").get_object(Bucket=bucket, Key=key)
        return pd.read_csv(io.BytesIO(obj["Body"].read()))
    return pd.read_csv(input_path)


def add_week_encoding(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["week_sin"] = np.sin(2 * np.pi * df["week_of_year"] / 52)
    df["week_cos"] = np.cos(2 * np.pi * df["week_of_year"] / 52)
    return df


def write_output(payload: dict, output_path: str) -> None:
    body = json.dumps(payload, indent=2)
    if output_path.startswith("s3://"):
        bucket, key = output_path[5:].split("/", 1)
        boto3.client("s3").put_object(Bucket=bucket, Key=key, Body=body.encode())
        logger.info("Wrote predictions to s3://%s/%s", bucket, key)
    else:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(body)
        logger.info("Wrote predictions to %s", output_path)


def main() -> None:
    args = parse_args()

    # Load model and metadata
    model_path = os.path.join(args.model_dir, "model.joblib")
    metadata_path = os.path.join(args.model_dir, "metadata.json")
    logger.info("Loading model from %s", model_path)
    model = joblib.load(model_path)
    with open(metadata_path) as f:
        metadata = json.load(f)

    feature_cols: list[str] = metadata["feature_cols"]
    label_classes: list[str] = metadata["label_classes"]
    high_threshold: float = metadata.get("best_high_threshold", 0.33)
    logger.info("Using High-class decision threshold: %.2f", high_threshold)

    # Load and prepare features
    logger.info("Loading features from %s", args.input_data)
    df = load_features(args.input_data)
    df = add_week_encoding(df)

    X = df[feature_cols]
    proba = model.predict_proba(X)  # [P(Low), P(Medium), P(High)]
    predictions = np.where(
        proba[:, 2] >= high_threshold,
        2,
        np.argmax(proba[:, :2], axis=1),
    )
    df["risk_level"] = [label_classes[p] for p in predictions]
    df["score"] = proba.max(axis=1)

    logger.info("Predictions:\n%s", df[["planning_area", "risk_level", "score"]].to_string())

    # Write predictions JSON to S3 (or local)
    payload = {
        "week": args.week,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "predictions": [
            {
                "planning_area": row["planning_area"],
                "risk_level": row["risk_level"],
                "score": round(float(row["score"]), 4),
            }
            for _, row in df.iterrows()
        ],
    }
    write_output(payload, args.output)
    logger.info("Wrote %d predictions for week %s", len(df), args.week)


if __name__ == "__main__":
    main()
