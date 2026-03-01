"""
Notification Stack
-------------------
Provisions:
  - SQS queue (risk-change events)
  - SNS topic (email delivery)
  - Lambda: risk-change detector (reads DB, pushes to SQS)
  - Lambda: SQS consumer → SNS publish
  - EventBridge rule triggering detector after inference
"""
from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import (
    aws_ec2 as ec2,
    aws_events as events,
    aws_events_targets as targets,
    aws_iam as iam,
    aws_lambda as lambda_,
    aws_lambda_event_sources as lambda_es,
    aws_secretsmanager as secretsmanager,
    aws_sns as sns,
    aws_sqs as sqs,
)
from constructs import Construct


class NotificationStack(cdk.Stack):
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
            self, "NotifLambdaSG",
            vpc=vpc,
            description="Security group for notification Lambda functions",
        )
        db_sg.add_ingress_rule(lambda_sg, ec2.Port.tcp(5432), "Notification Lambda to RDS")

        # ── SQS Queue ─────────────────────────────────────────────────────
        dlq = sqs.Queue(self, "RiskChangeDLQ", retention_period=cdk.Duration.days(14))
        queue = sqs.Queue(
            self, "RiskChangeQueue",
            queue_name="risk-change-queue",
            visibility_timeout=cdk.Duration.seconds(60),
            dead_letter_queue=sqs.DeadLetterQueue(max_receive_count=3, queue=dlq),
        )

        # ── SNS Topic ─────────────────────────────────────────────────────
        topic = sns.Topic(self, "DengueNotificationsTopic", display_name="DengueWatch Alerts")

        # ── Risk-Change Detector Lambda ───────────────────────────────────
        detector_fn = lambda_.Function(
            self, "RiskChangeDetectorFunction",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="handler.handler",
            code=lambda_.Code.from_asset("../backend/notifications"),
            environment={
                "DB_SECRET_ARN": db_secret.secret_arn,
                "SQS_QUEUE_URL": queue.queue_url,
            },
            vpc=vpc,
            security_groups=[lambda_sg],
            timeout=cdk.Duration.minutes(5),
        )
        db_secret.grant_read(detector_fn)
        queue.grant_send_messages(detector_fn)

        # EventBridge: fire 30 minutes after SageMaker inference at Monday 06:30 SGT (Sunday 22:30 UTC)
        events.Rule(
            self, "PostInferenceNotifyRule",
            schedule=events.Schedule.cron(
                minute="30", hour="22", week_day="SUN", month="*", year="*"
            ),
            targets=[targets.LambdaFunction(detector_fn)],
        )

        # ── SQS → SNS Forwarder Lambda ────────────────────────────────────
        forwarder_fn = lambda_.Function(
            self, "SqsToSnsForwarderFunction",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="index.handler",
            code=lambda_.Code.from_inline(
                "import boto3, json, os\n"
                "def handler(event, context):\n"
                "    sns = boto3.client('sns')\n"
                "    for record in event['Records']:\n"
                "        msg = json.loads(record['body'])\n"
                "        sns.publish(\n"
                "            TopicArn=os.environ['SNS_TOPIC_ARN'],\n"
                "            Subject=f\"DengueWatch Alert: {msg['planningArea']}\",\n"
                "            Message=(\n"
                "                f\"Risk in {msg['planningArea']} has changed from \"\n"
                "                f\"{msg['previousRisk']} to {msg['currentRisk']} \"\n"
                "                f\"for week {msg['week']}.\"\n"
                "            ),\n"
                "        )\n"
            ),
            environment={"SNS_TOPIC_ARN": topic.topic_arn},
            timeout=cdk.Duration.seconds(30),
        )
        topic.grant_publish(forwarder_fn)
        forwarder_fn.add_event_source(
            lambda_es.SqsEventSource(queue, batch_size=10)
        )

        cdk.CfnOutput(self, "SqsQueueUrl", value=queue.queue_url)
        cdk.CfnOutput(self, "SnsTopicArn", value=topic.topic_arn)
