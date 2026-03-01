"""
Frontend Stack
---------------
Provisions:
  - S3 bucket (static website)
  - CloudFront distribution (HTTPS, OAC)
  - Deployment of the Vite build output
"""
from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import (
    aws_s3 as s3,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    aws_s3_deployment as s3deploy,
)
from constructs import Construct


class FrontendStack(cdk.Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        api_url: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ── S3 Bucket ─────────────────────────────────────────────────────
        bucket = s3.Bucket(
            self, "FrontendBucket",
            removal_policy=cdk.RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
        )

        # ── CloudFront OAC ────────────────────────────────────────────────
        oac = cloudfront.S3OriginAccessControl(
            self, "OAC",
            description="DengueWatch frontend OAC",
        )

        distribution = cloudfront.Distribution(
            self, "Distribution",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3BucketOrigin.with_origin_access_control(
                    bucket, origin_access_control=oac
                ),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
            ),
            default_root_object="index.html",
            error_responses=[
                cloudfront.ErrorResponse(
                    http_status=404,
                    response_http_status=200,
                    response_page_path="/index.html",
                ),
            ],
        )

        # ── Deploy built assets ───────────────────────────────────────────
        s3deploy.BucketDeployment(
            self, "DeployFrontend",
            sources=[s3deploy.Source.asset("../frontend/dist")],
            destination_bucket=bucket,
            distribution=distribution,
            distribution_paths=["/*"],
        )

        cdk.CfnOutput(
            self, "CloudFrontUrl",
            value=f"https://{distribution.domain_name}",
            description="CloudFront distribution URL",
        )
        cdk.CfnOutput(self, "ApiUrl", value=api_url, description="Backend API URL")
