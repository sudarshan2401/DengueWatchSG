"""
SageMaker XGBoost Training Script
-----------------------------------
Trains a multi-class XGBoost classifier to predict dengue risk level
(Low / Medium / High) for each Singapore planning area.

Features
--------
  - lag_cases_1w … lag_cases_4w  : lagged dengue case counts (1–4 weeks prior)
  - lag_rainfall_2w, lag_rainfall_3w : lagged mean rainfall
  - lag_temp_2w, lag_temp_3w     : lagged mean temperature
  - week_of_year                 : sine/cosine encoding for seasonality

Usage (SageMaker training job)
------------------------------
    python train.py \
        --train       /opt/ml/input/data/train/train.csv \
        --validation  /opt/ml/input/data/validation/validation.csv \
        --model-dir   /opt/ml/model \
        --n-estimators 200 \
        --max-depth 6 \
        --learning-rate 0.1
"""
from __future__ import annotations

import argparse
import os
import json
import logging
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import classification_report
import joblib

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

LABEL_CLASSES = ["Low", "Medium", "High"]
FEATURE_COLS = [
    "lag_cases_1w", "lag_cases_2w", "lag_cases_3w", "lag_cases_4w",
    "lag_rainfall_2w", "lag_rainfall_3w",
    "lag_temp_2w", "lag_temp_3w",
    "week_sin", "week_cos",
]
TARGET_COL = "risk_level"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", default=os.environ.get("SM_CHANNEL_TRAIN", "data/train.csv"))
    parser.add_argument("--validation", default=os.environ.get("SM_CHANNEL_VALIDATION", "data/validation.csv"))
    parser.add_argument("--model-dir", default=os.environ.get("SM_MODEL_DIR", "model"))
    parser.add_argument("--n-estimators", type=int, default=200)
    parser.add_argument("--max-depth", type=int, default=6)
    parser.add_argument("--learning-rate", type=float, default=0.1)
    parser.add_argument("--subsample", type=float, default=0.8)
    return parser.parse_args()


def add_week_encoding(df: pd.DataFrame) -> pd.DataFrame:
    """Add sine/cosine encoding of week_of_year."""
    df = df.copy()
    df["week_sin"] = np.sin(2 * np.pi * df["week_of_year"] / 52)
    df["week_cos"] = np.cos(2 * np.pi * df["week_of_year"] / 52)
    return df


def load_data(path: str) -> tuple[pd.DataFrame, pd.Series]:
    df = pd.read_csv(path)
    df = add_week_encoding(df)
    le = LabelEncoder()
    le.fit(LABEL_CLASSES)
    y = le.transform(df[TARGET_COL])
    X = df[FEATURE_COLS]
    return X, pd.Series(y, name=TARGET_COL)


def main() -> None:
    args = parse_args()
    os.makedirs(args.model_dir, exist_ok=True)

    logger.info("Loading training data from %s", args.train)
    X_train, y_train = load_data(args.train)

    logger.info("Loading validation data from %s", args.validation)
    X_val, y_val = load_data(args.validation)

    model = xgb.XGBClassifier(
        n_estimators=args.n_estimators,
        max_depth=args.max_depth,
        learning_rate=args.learning_rate,
        subsample=args.subsample,
        objective="multi:softmax",
        num_class=3,
        eval_metric="mlogloss",
        use_label_encoder=False,
        random_state=42,
    )

    logger.info("Training model…")
    model.fit(
        X_train, y_train,
        eval_set=[(X_val, y_val)],
        verbose=50,
    )

    # Evaluate
    y_pred = model.predict(X_val)
    report = classification_report(y_val, y_pred, target_names=LABEL_CLASSES)
    logger.info("Validation classification report:\n%s", report)

    # Save artifacts    model_path = os.path.join(args.model_dir, "model.joblib")
    joblib.dump(model, model_path)
    logger.info("Model saved to %s", model_path)

    metadata = {
        "feature_cols": FEATURE_COLS,
        "label_classes": LABEL_CLASSES,
        "hyperparameters": {
            "n_estimators": args.n_estimators,
            "max_depth": args.max_depth,
            "learning_rate": args.learning_rate,
            "subsample": args.subsample,
        },
    }
    with open(os.path.join(args.model_dir, "metadata.json"), "w") as f:
        json.dump(metadata, f, indent=2)


if __name__ == "__main__":
    main()
