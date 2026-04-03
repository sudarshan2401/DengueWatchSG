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
from sklearn.metrics import classification_report, f1_score
import joblib

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

LABEL_CLASSES = ["Low", "Medium", "High"]
FEATURE_COLS = [
    "lag_cases_1w", "lag_cases_2w", "lag_cases_3w", "lag_cases_4w",
    "lag_cases_5w", "lag_cases_6w", "lag_cases_7w", "lag_cases_8w",
    "lag_national_1w", "lag_national_2w",
    "lag_rainfall_2w", "lag_rainfall_3w", "lag_rainfall_4w",
    "lag_temp_2w", "lag_temp_3w", "lag_temp_4w",
    "week_sin", "week_cos",
]
TARGET_COL = "risk_level"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", default=os.environ.get("SM_CHANNEL_TRAIN", "data/train.csv"))
    parser.add_argument("--validation", default=os.environ.get("SM_CHANNEL_VALIDATION", "data/validation.csv"))
    parser.add_argument("--model-dir", default=os.environ.get("SM_MODEL_DIR", "model"))
    parser.add_argument("--n-estimators", type=int, default=1000)
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


LABEL_MAP = {"Low": 0, "Medium": 1, "High": 2}  # explicit, not alphabetical


def load_data(path: str) -> tuple[pd.DataFrame, pd.Series]:
    df = pd.read_csv(path)
    df = add_week_encoding(df)
    y = df[TARGET_COL].map(LABEL_MAP)
    X = df[FEATURE_COLS]
    return X, y


def main() -> None:
    args = parse_args()
    os.makedirs(args.model_dir, exist_ok=True)

    logger.info("Loading training data from %s", args.train)
    X_train, y_train = load_data(args.train)

    logger.info("Loading validation data from %s", args.validation)
    X_val, y_val = load_data(args.validation)

    # Compute per-sample weights to counter class imbalance.
    # Each sample is weighted by (n_samples / (n_classes * class_count)).
    class_counts = np.bincount(y_train, minlength=3)
    logger.info("Train class counts — Low: %d, Medium: %d, High: %d", *class_counts)
    weights = len(y_train) / (3 * class_counts)
    sample_weights = weights[y_train]
    logger.info("Class weights — Low: %.3f, Medium: %.3f, High: %.3f", *weights)

    model = xgb.XGBClassifier(
        n_estimators=args.n_estimators,
        max_depth=args.max_depth,
        learning_rate=args.learning_rate,
        subsample=args.subsample,
        objective="multi:softmax",
        num_class=3,
        eval_metric="mlogloss",
        early_stopping_rounds=50,
        use_label_encoder=False,
        random_state=42,
    )

    logger.info("Training model (max %d rounds, early stopping after 50 no-improve)…",
                args.n_estimators)
    model.fit(
        X_train, y_train,
        sample_weight=sample_weights,
        eval_set=[(X_val, y_val)],
        verbose=50,
    )
    logger.info("Best iteration: %d (validation mlogloss: %.5f)",
                model.best_iteration, model.best_score)

    # Evaluate at default threshold
    y_pred = model.predict(X_val)
    report = classification_report(y_val, y_pred, target_names=LABEL_CLASSES)
    logger.info("Validation classification report:\n%s", report)

    # Threshold sweep — lower the High decision threshold to improve recall
    # model.predict_proba returns [P(Low), P(Medium), P(High)] per row
    y_proba = model.predict_proba(X_val)
    logger.info("Threshold sweep for High-class recall (class index 2):")
    logger.info("  threshold | macro-F1 | High-prec | High-recall | High-F1")
    best_threshold = 0.33
    best_macro_f1 = 0.0
    for thresh in np.arange(0.10, 0.55, 0.05):
        # Assign High if P(High) >= thresh, else argmax of remaining
        y_t = np.where(
            y_proba[:, 2] >= thresh,
            2,
            np.argmax(y_proba[:, :2], axis=1),
        )
        macro_f1 = f1_score(y_val, y_t, average="macro", zero_division=0)
        high_mask = (y_val == 2) | (y_t == 2)
        if high_mask.sum() == 0:
            high_p = high_r = high_f = 0.0
        else:
            high_p = float(((y_t == 2) & (y_val == 2)).sum() / max((y_t == 2).sum(), 1))
            high_r = float(((y_t == 2) & (y_val == 2)).sum() / max((y_val == 2).sum(), 1))
            high_f = (2 * high_p * high_r / (high_p + high_r)) if (high_p + high_r) > 0 else 0.0
        logger.info("  %.2f      | %.3f    | %.3f     | %.3f       | %.3f",
                    thresh, macro_f1, high_p, high_r, high_f)
        if macro_f1 > best_macro_f1:
            best_macro_f1 = macro_f1
            best_threshold = thresh
    logger.info("Best threshold by macro-F1: %.2f (macro-F1=%.3f)", best_threshold, best_macro_f1)

    # Save artifacts
    model_path = os.path.join(args.model_dir, "model.joblib")
    joblib.dump(model, model_path)
    logger.info("Model saved to %s", model_path)

    metadata = {
        "feature_cols": FEATURE_COLS,
        "label_classes": LABEL_CLASSES,
        "best_high_threshold": round(float(best_threshold), 2),
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
