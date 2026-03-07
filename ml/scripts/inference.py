"""
SageMaker Batch Inference Script
----------------------------------
Runs weekly batch inference using the trained XGBoost model.
Reads feature data from S3, writes risk predictions back to RDS.

Usage (SageMaker Processing Job / standalone)
---------------------------------------------
    python inference.py \
        --model-dir   /opt/ml/model \
        --input-data  s3://my-bucket/features/latest.csv \
        --week        2024-W10
"""
from __future__ import annotations

import argparse
import os
import json
import logging
import io
import numpy as np
import pandas as pd
import boto3
import psycopg2
import joblib

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

RISK_LABELS = ["Low", "Medium", "High"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", default=os.environ.get("SM_MODEL_DIR", "model"))
    parser.add_argument("--input-data", required=True, help="S3 URI or local path to features CSV")
    parser.add_argument("--week", required=True, help="ISO week string, e.g. 2024-W10")
    parser.add_argument("--db-host", default=os.environ.get("DB_HOST", "localhost"))
    parser.add_argument("--db-port", type=int, default=int(os.environ.get("DB_PORT", 5432)))
    parser.add_argument("--db-name", default=os.environ.get("DB_NAME", "denguewatch"))
    parser.add_argument("--db-user", default=os.environ.get("DB_USER", "postgres"))
    parser.add_argument("--db-password", default=os.environ.get("DB_PASSWORD", "postgres"))
    return parser.parse_args()


def load_features(input_path: str) -> pd.DataFrame:
    if input_path.startswith("s3://"):
        s3 = boto3.client("s3")
        bucket, key = input_path[5:].split("/", 1)
        obj = s3.get_object(Bucket=bucket, Key=key)
        return pd.read_csv(io.BytesIO(obj["Body"].read()))
    return pd.read_csv(input_path)


def add_week_encoding(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["week_sin"] = np.sin(2 * np.pi * df["week_of_year"] / 52)
    df["week_cos"] = np.cos(2 * np.pi * df["week_of_year"] / 52)
    return df


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
    # Use tuned High threshold if available, otherwise fall back to argmax (0.33)
    high_threshold: float = metadata.get("best_high_threshold", 0.33)
    logger.info("Using High-class decision threshold: %.2f", high_threshold)

    # Load features
    logger.info("Loading features from %s", args.input_data)
    df = load_features(args.input_data)
    df = add_week_encoding(df)

    X = df[feature_cols]
    proba = model.predict_proba(X)  # shape (n, 3): [P(Low), P(Medium), P(High)]
    # Apply tuned threshold: flag High if P(High) >= threshold, else argmax of Low/Medium
    import numpy as np
    predictions = np.where(
        proba[:, 2] >= high_threshold,
        2,
        np.argmax(proba[:, :2], axis=1),
    )
    df["risk_level"] = [label_classes[p] for p in predictions]
    df["score"] = proba.max(axis=1)

    logger.info("Predictions:\n%s", df[["planning_area", "risk_level", "score"]].to_string())

    # Write to RDS
    conn = psycopg2.connect(
        host=args.db_host,
        port=args.db_port,
        dbname=args.db_name,
        user=args.db_user,
        password=args.db_password,
    )
    try:
        with conn.cursor() as cur:
            for _, row in df.iterrows():
                cur.execute(
                    """
                    INSERT INTO planning_area_risk (planning_area, risk_level, score, week)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (planning_area, week)
                    DO UPDATE SET risk_level = EXCLUDED.risk_level,
                                  score = EXCLUDED.score,
                                  created_at = NOW()
                    """,
                    (row["planning_area"], row["risk_level"], float(row["score"]), args.week),
                )
        conn.commit()
        logger.info("Wrote %d predictions for week %s", len(df), args.week)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
