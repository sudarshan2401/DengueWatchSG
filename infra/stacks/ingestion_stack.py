"""
Data Ingestion Stack
---------------------
Provisions:
  - Lambda: daily ETL pulling from NEA data.gov.sg API
  - EventBridge rule (daily schedule)
  - Secrets Manager secret for NEA API key
"""
from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import (
    aws_ec2 as ec2,
    aws_events as events,
    aws_events_targets as targets,
    aws_lambda as lambda_,
    aws_secretsmanager as secretsmanager,
)
from constructs import Construct


class IngestionStack(cdk.Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        db_secret: secretsmanager.ISecret,
        db_sg: ec2.ISecurityGroup,
        vpc: ec2.IVpc,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        lambda_sg = ec2.SecurityGroup(
            self, "IngestionLambdaSG",
            vpc=vpc,
            description="Security group for data ingestion Lambda",
        )
        db_sg.add_ingress_rule(lambda_sg, ec2.Port.tcp(5432), "Ingestion Lambda to RDS")

        # NEA API key secret
        nea_secret = secretsmanager.Secret(
            self, "NeaApiKeySecret",
            secret_name="denguewatch/nea-api-key",
            description="NEA data.gov.sg API key",
        )

        # ── Ingestion Lambda ──────────────────────────────────────────────
        ingestion_fn = lambda_.Function(
            self, "DataIngestionFunction",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="handler.handler",
            code=lambda_.Code.from_asset("../data-ingestion"),
            environment={
                "DB_SECRET_ARN": db_secret.secret_arn,
                "NEA_SECRET_ARN": nea_secret.secret_arn,
            },
            vpc=vpc,
            security_groups=[lambda_sg],
            timeout=cdk.Duration.minutes(5),
            memory_size=512,
        )
        db_secret.grant_read(ingestion_fn)
        nea_secret.grant_read(ingestion_fn)

        # ── EventBridge: daily at 01:00 SGT (which is 17:00 UTC on the previous day due to UTC+8 offset) ──
        events.Rule(
            self, "DailyIngestionRule",
            schedule=events.Schedule.cron(
                minute="0", hour="17", month="*", week_day="*", year="*"
            ),
            targets=[targets.LambdaFunction(ingestion_fn)],
        )
