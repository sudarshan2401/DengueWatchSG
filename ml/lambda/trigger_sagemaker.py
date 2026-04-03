"""
DengueWatch SG — SageMaker Trigger Lambda
------------------------------------------
Triggered by EventBridge every Monday at 16:30 UTC (00:30 SGT Tuesday),
30 minutes after the ingestion Lambdas run.

Starts a SageMaker Processing Job that runs run_weekly.py inside
the denguewatch-ml container.

Environment variables:
  SAGEMAKER_ROLE_ARN  — IAM role ARN for SageMaker
  IMAGE_URI           — ECR image URI for the ML container
  DATA_BUCKET         — S3 bucket (default: dengue-ml-data-lake)
"""
import os
import boto3
from datetime import datetime, timezone


def handler(event, context):
    today = datetime.now(timezone.utc)
    iso = today.isocalendar()
    week = f"{iso[0]}-W{iso[1]:02d}"
    timestamp = today.strftime("%H%M%S")
    job_name = f"denguewatch-{week.replace('-', '').replace('W', 'w')}-{timestamp}"

    bucket = os.environ.get("DATA_BUCKET", "dengue-ml-data-lake")
    role_arn = os.environ["SAGEMAKER_ROLE_ARN"]
    image_uri = os.environ["IMAGE_URI"]

    sm = boto3.client("sagemaker", region_name="ap-southeast-1")
    sm.create_processing_job(
        ProcessingJobName=job_name,
        ProcessingResources={
            "ClusterConfig": {
                "InstanceCount": 1,
                "InstanceType": "ml.t3.medium",
                "VolumeSizeInGB": 10,
            }
        },
        AppSpecification={
            "ImageUri": image_uri,
            "ContainerEntrypoint": ["python3", "/opt/ml/code/scripts/run_weekly.py"],
        },
        Environment={
            "WEEK": week,
            "DATA_BUCKET": bucket,
            "OUTPUT_BUCKET": os.environ.get("OUTPUT_BUCKET", "dengue-ml-predictions"),
        },
        RoleArn=role_arn,
    )

    print(f"Started SageMaker Processing Job: {job_name} for week {week}")
    return {"week": week, "job_name": job_name, "status": "triggered"}
