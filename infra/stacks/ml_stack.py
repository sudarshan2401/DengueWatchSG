"""
ML Stack
---------
Provisions:
  - S3 bucket for training data and model artefacts
  - SageMaker execution role
  - EventBridge rule triggering weekly batch inference
  - Lambda to kick off the SageMaker Processing Job
"""
from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import (
    aws_s3 as s3,
    aws_iam as iam,
    aws_events as events,
    aws_events_targets as targets,
    aws_lambda as lambda_,
)
from constructs import Construct


class MlStack(cdk.Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ── S3 bucket for ML data / artifacts ─────────────────────────────
        self.ml_bucket = s3.Bucket(
            self, "MlBucket",
            removal_policy=cdk.RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            versioned=True,
            encryption=s3.BucketEncryption.S3_MANAGED,
        )

        # ── SageMaker execution role ──────────────────────────────────────
        self.sagemaker_role = iam.Role(
            self, "SageMakerRole",
            assumed_by=iam.ServicePrincipal("sagemaker.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonSageMakerFullAccess"
                )
            ],
        )
        self.ml_bucket.grant_read_write(self.sagemaker_role)

        # ── Lambda to trigger SageMaker inference job ─────────────────────
        trigger_fn = lambda_.Function(
            self, "InferenceTriggerFunction",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="index.handler",
            code=lambda_.Code.from_inline(
                # Placeholder: replace with a proper asset in production
                "import boto3, os\n"
                "def handler(event, context):\n"
                "    sm = boto3.client('sagemaker')\n"
                "    # TODO: start SageMaker Processing Job\n"
                "    print('Inference trigger fired')\n"
            ),
            environment={
                "ML_BUCKET": self.ml_bucket.bucket_name,
                "SAGEMAKER_ROLE_ARN": self.sagemaker_role.role_arn,
            },
            timeout=cdk.Duration.minutes(5),
        )
        self.ml_bucket.grant_read(trigger_fn)
        trigger_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["sagemaker:CreateProcessingJob"],
                resources=["*"],
            )
        )

        # ── EventBridge: every Monday at 06:00 SGT (which is Sunday 22:00 UTC due to UTC+8 offset) ──
        events.Rule(
            self, "WeeklyInferenceRule",
            schedule=events.Schedule.cron(
                minute="0", hour="22", week_day="SUN", month="*", year="*"
            ),
            targets=[targets.LambdaFunction(trigger_fn)],
        )

        cdk.CfnOutput(
            self, "MlBucketName",
            value=self.ml_bucket.bucket_name,
            description="S3 bucket for ML artifacts",
        )
