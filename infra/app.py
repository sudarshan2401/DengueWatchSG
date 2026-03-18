#!/usr/bin/env python3
"""
DengueWatch SG — AWS CDK Application Entry Point
"""
import aws_cdk as cdk
from stacks.database_stack import DatabaseStack
from stacks.backend_stack import BackendStack
from stacks.frontend_stack import FrontendStack
from stacks.ml_stack import MlStack
from stacks.notification_stack import NotificationStack
from stacks.ingestion_stack import IngestionStack

app = cdk.App()

env = cdk.Environment(
    account=app.node.try_get_context("account"),
    region=app.node.try_get_context("region") or "ap-southeast-1",
)

# ── Layer 1: Database ─────────────────────────────────────────────────────
db_stack = DatabaseStack(app, "DengueWatchDB", env=env)

# ── Layer 2: ML ───────────────────────────────────────────────────────────
ml_stack = MlStack(app, "DengueWatchML", env=env)

# ── Layer 3: Data Ingestion ───────────────────────────────────────────────
ingestion_stack = IngestionStack(
    app, "DengueWatchIngestion",
    db_secret=db_stack.db_secret,
    db_sg=db_stack.db_sg,
    vpc=db_stack.vpc,
    env=env,
)

# ── Layer 4: Backend (API Gateway + Lambda) ───────────────────────────────
backend_stack = BackendStack(
    app, "DengueWatchBackend",
    db_secret=db_stack.db_secret,
    db_sg=db_stack.db_sg,
    vpc=db_stack.vpc,
    env=env,
)

# ── Layer 5: Notification System ─────────────────────────────────────────
notification_stack = NotificationStack(
    app, "DengueWatchNotifications",
    db_secret=db_stack.db_secret,
    db_sg=db_stack.db_sg,
    vpc=db_stack.vpc,
    env=env,
)

# ── Layer 6: Frontend (S3 + CloudFront) ──────────────────────────────────
frontend_stack = FrontendStack(
    app, "DengueWatchFrontend",
    api_url="https://vod0qxda75.execute-api.ap-southeast-1.amazonaws.com/default/dengue-api",
    env=env,
)

app.synth()
