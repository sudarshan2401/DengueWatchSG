"""
Backend Stack
--------------
Provisions:
  - API Gateway (REST)
  - Lambda functions: risk_map, subscriptions
  - IAM roles with Secrets Manager access
"""
from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import (
    aws_apigateway as apigw,
    aws_ec2 as ec2,
    aws_lambda as lambda_,
    aws_secretsmanager as secretsmanager,
)
from constructs import Construct


class BackendStack(cdk.Stack):
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
            self, "LambdaSG",
            vpc=vpc,
            description="Security group for backend Lambda functions",
        )
        # Allow Lambda → RDS
        db_sg.add_ingress_rule(lambda_sg, ec2.Port.tcp(5432), "Lambda to RDS")

        common_env = {
            "DB_SECRET_ARN": db_secret.secret_arn,
        }

        # ── Risk Map Lambda ───────────────────────────────────────────────
        risk_map_fn = lambda_.Function(
            self, "RiskMapFunction",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="handler.handler",
            code=lambda_.Code.from_asset("../backend/risk_map"),
            environment=common_env,
            vpc=vpc,
            security_groups=[lambda_sg],
            timeout=cdk.Duration.seconds(30),
        )
        db_secret.grant_read(risk_map_fn)

        # ── Subscriptions Lambda ──────────────────────────────────────────
        subscriptions_fn = lambda_.Function(
            self, "SubscriptionsFunction",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="handler.handler",
            code=lambda_.Code.from_asset("../backend/subscriptions"),
            environment=common_env,
            vpc=vpc,
            security_groups=[lambda_sg],
            timeout=cdk.Duration.seconds(30),
        )
        db_secret.grant_read(subscriptions_fn)

        # ── API Gateway ───────────────────────────────────────────────────
        api = apigw.RestApi(
            self, "DengueWatchApi",
            rest_api_name="DengueWatch API",
            default_cors_preflight_options=apigw.CorsOptions(
                allow_origins=apigw.Cors.ALL_ORIGINS,
                allow_methods=apigw.Cors.ALL_METHODS,
            ),
        )

        risk_map_resource = api.root.add_resource("risk-map")
        risk_map_resource.add_method(
            "GET", apigw.LambdaIntegration(risk_map_fn)
        )

        postal_code_resource = api.root.add_resource("postal-code").add_resource("{code}")
        postal_code_resource.add_method(
            "GET", apigw.LambdaIntegration(risk_map_fn)
        )

        subscriptions_resource = api.root.add_resource("subscriptions")
        subscriptions_resource.add_method(
            "POST", apigw.LambdaIntegration(subscriptions_fn)
        )
        subscriptions_resource.add_method(
            "GET", apigw.LambdaIntegration(subscriptions_fn)
        )

        self.api_url = api.url

        cdk.CfnOutput(self, "ApiUrl", value=api.url, description="API Gateway base URL")
