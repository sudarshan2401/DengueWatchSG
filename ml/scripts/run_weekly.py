"""
DengueWatch SG — Weekly ML Job Entrypoint
------------------------------------------
Runs inside the SageMaker Processing Job container.
Downloads model from S3, runs build_features.py then inference.py.

Environment variables (set by trigger Lambda):
  WEEK            — ISO week string, e.g. 2026-W12
  DATA_BUCKET     — S3 bucket with raw ingestion data (default: dengue-ml-data-lake)
  OUTPUT_BUCKET   — S3 bucket for features + predictions (default: dengue-ml-predictions)
"""
import os
import subprocess
import sys
import boto3

WEEK = os.environ["WEEK"]
DATA_BUCKET = os.environ.get("DATA_BUCKET", "dengue-ml-data-lake")
OUTPUT_BUCKET = os.environ.get("OUTPUT_BUCKET", "dengue-ml-predictions")
MODEL_DIR = "/opt/ml/code/model"
DATA_DIR = "/opt/ml/code/data"
CODE_DIR = "/opt/ml/code/scripts"

# Download model artifacts from S3
print(f"Downloading model artifacts from s3://{DATA_BUCKET}/model/")
os.makedirs(MODEL_DIR, exist_ok=True)
s3 = boto3.client("s3")
for filename in ["model.joblib", "metadata.json"]:
    s3.download_file(DATA_BUCKET, f"model/{filename}", f"{MODEL_DIR}/{filename}")
    print(f"  Downloaded {filename}")

# Step 1: Build features
print(f"\n[1/2] Building features for week {WEEK}...")
subprocess.run([
    sys.executable, f"{CODE_DIR}/build_features.py",
    "--bucket", DATA_BUCKET,
    "--week", WEEK,
    "--output", f"s3://{OUTPUT_BUCKET}/features/week={WEEK}/features.csv",
    "--data-dir", DATA_DIR,
], check=True)

# Step 2: Run inference
print(f"\n[2/2] Running inference for week {WEEK}...")
subprocess.run([
    sys.executable, f"{CODE_DIR}/inference.py",
    "--model-dir", MODEL_DIR,
    "--input-data", f"s3://{OUTPUT_BUCKET}/features/week={WEEK}/features.csv",
    "--output", f"s3://{OUTPUT_BUCKET}/predictions/week={WEEK}/results.json",
    "--week", WEEK,
], check=True)

print(f"\nDone. Predictions written to s3://{OUTPUT_BUCKET}/predictions/week={WEEK}/results.json")
