"""
Database Stack
--------------
Provisions:
  - VPC (2 AZs, public + private subnets)
  - RDS PostgreSQL (Multi-AZ in prod)
  - Secrets Manager secret for DB credentials
"""
from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import (
    aws_ec2 as ec2,
    aws_rds as rds,
    aws_secretsmanager as secretsmanager,
)
from constructs import Construct


class DatabaseStack(cdk.Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ── VPC ──────────────────────────────────────────────────────────
        self.vpc = ec2.Vpc(
            self, "VPC",
            max_azs=2,
            nat_gateways=1,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="Public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24,
                ),
                ec2.SubnetConfiguration(
                    name="Private",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=24,
                ),
                ec2.SubnetConfiguration(
                    name="Isolated",
                    subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
                    cidr_mask=24,
                ),
            ],
        )

        # ── Security Group for RDS ────────────────────────────────────────
        self.db_sg = ec2.SecurityGroup(
            self, "DbSecurityGroup",
            vpc=self.vpc,
            description="DengueWatch RDS security group",
        )

        # ── Secrets Manager ───────────────────────────────────────────────
        self.db_secret = secretsmanager.Secret(
            self, "DbSecret",
            secret_name="denguewatch/db-credentials",
            generate_secret_string=secretsmanager.SecretStringGenerator(
                secret_string_template='{"username": "denguewatch"}',
                generate_string_key="password",
                exclude_characters="@/\"",
            ),
        )

        # ── RDS PostgreSQL ────────────────────────────────────────────────
        rds.DatabaseInstance(
            self, "RdsInstance",
            engine=rds.DatabaseInstanceEngine.postgres(
                version=rds.PostgresEngineVersion.VER_15_4
            ),
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.BURSTABLE3, ec2.InstanceSize.MEDIUM
            ),
            vpc=self.vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED),
            security_groups=[self.db_sg],
            credentials=rds.Credentials.from_secret(self.db_secret),
            database_name="denguewatch",
            multi_az=False,           # set True for production
            storage_encrypted=True,
            deletion_protection=False,  # set True for production
            removal_policy=cdk.RemovalPolicy.DESTROY,  # use RETAIN for production
        )
