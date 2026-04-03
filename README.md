# DengueWatch SG

A dengue risk prediction web platform for Singapore, providing real-time risk maps, postal code monitoring, and email notifications when risk levels change.

## Architecture Overview

| Layer | Technology |
|---|---|
| Frontend | React (TypeScript) + Vite, hosted on AWS S3 + CloudFront |
| Backend | Python, AWS API Gateway + Lambda |
| Database | Amazon RDS (PostgreSQL) |
| ML Pipeline | Python, Amazon SageMaker (XGBoost weekly batch inference) |
| Data Ingestion | AWS Lambda (Python ETL) pulling from data.gov.sg API |
| Risk Ingestion | AWS Lambda triggered by S3 — upserts ML predictions into RDS |
| Notifications | S3 → SNS → Dispatcher Lambda → SQS → Worker Lambda → Amazon SES |
| OneMap | AWS Lambda auto-refreshes JWT token into SSM Parameter Store every day |
| IaC | AWS CDK (Python) |
| Local Dev | Docker + docker-compose |

## Monorepo Structure

```
cs5224/
├── frontend/          # React + TypeScript + Vite web application
├── backend/           # AWS Lambda functions (REST API)
│   ├── risk_map/      # GET /risk — returns current weekly risk scores
│   │   └── ingestion/ # S3-triggered Lambda that upserts ML predictions into RDS
│   ├── postal_code/   # GET /postal-code/{code} — resolves postal code via OneMap
│   ├── planning_areas/# GET /planning-areas — returns GeoJSON boundaries from OneMap
│   ├── subscriptions/ # POST/GET /subscribe — manage email subscriptions
│   ├── onemap_refresher/ # EventBridge-scheduled Lambda to refresh OneMap token in SSM
│   └── db/            # init.sql database schema
├── notification/      # Standalone notification service (Dispatcher + Worker Lambdas)
│   ├── dispatcher/    # S3 → SQS: identifies affected subscribers, batches into SQS
│   └── worker/        # SQS → SES: sends HTML alert emails via Amazon SES
├── ml/                # SageMaker training & inference scripts
├── infra/             # AWS CDK infrastructure-as-code
├── data-ingestion/    # ETL Lambdas pulling from data.gov.sg
│   ├── lambdas/       # One folder per Lambda function
│   │   ├── dengue/    # Lambda code for pulling dengue clusters
│   │   └── weather/   # Lambda code for pulling rainfall and air temperature
│   ├── eventbridge/   # EventBridge schedule rule (CloudFormation template)
│   └── iam/           # IAM policy for S3 write access
├── docker-compose.yml # Local development environment
└── README.md
```

## Getting Started

### Prerequisites

- Node.js 18+
- Python 3.11+
- Docker & Docker Compose
- AWS CLI configured
- AWS CDK CLI (`npm install -g aws-cdk`)

### Local Development

```bash
# Start all services locally
docker-compose up --build

# Frontend only (http://localhost:5173)
cd frontend && npm install && npm run dev

# Backend only (http://localhost:8000)
cd backend && pip install -r requirements.txt && python local_server.py
```

### Deploying Infrastructure

```bash
cd infra
pip install -r requirements.txt
cdk bootstrap
cdk deploy --all
```

### Deploying the Notification Service

```bash
cd notification
./deploy.sh
```

## Frontend Pages

1. **Landing Page** (`/`) — Interactive choropleth map of Singapore planning areas colour-coded by predicted dengue risk (Low / Medium / High), postal code search bar, and notification bell icon.
2. **Notification Subscription Page** (`/subscribe`) — Users enter their email address and add postal codes to monitor for risk changes.

## Backend API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/risk` | Current weekly risk scores for all planning areas (served via CloudFront CDN) |
| `GET` | `/postal-code/{code}` | Resolve a Singapore postal code to a planning area and coordinates via OneMap |
| `GET` | `/planning-areas` | GeoJSON FeatureCollection of Singapore planning area boundaries from OneMap |
| `POST` | `/subscribe` | Create or update an email subscription with planning areas to monitor |
| `GET` | `/subscribe` | List all subscriptions (admin use only) |

The `/risk` endpoint is fronted by a separate CloudFront distribution with a 2-day cache TTL (`Cache-Control: max-age=172800`). All other endpoints go through the API Gateway directly.

## OneMap Token Management

Planning area boundary and postal code lookups use the OneMap API, which requires a JWT. A dedicated **OneMap Token Refresher** Lambda runs daily (EventBridge) to fetch a fresh token using credentials stored in AWS SSM Parameter Store (`/denguewatch/onemap/email`, `/denguewatch/onemap/password`) and writes the new token back to SSM (`/denguewatch/onemap/token`). If a 401 is received at runtime, the API Lambdas automatically invoke the refresher and retry once.

## ML Pipeline

- **Scheduler**: Amazon EventBridge triggers a weekly SageMaker batch inference job every Monday at 06:00 SGT.
- **Features**: lagged dengue case counts (1–4 weeks), lagged rainfall/temperature (2–3 weeks), sine/cosine week-of-year encoding.
- **Model**: XGBoost multi-class classifier (Low / Medium / High).
- **Output**: SageMaker writes `predictions.json` to S3, which triggers downstream ingestion and notifications.

## Risk Map Ingestion

An S3-triggered Lambda (`backend/risk_map/ingestion/`) listens for new `predictions.json` objects via SNS. It validates the JSON schema, parses each record into a `PredictionRecord` dataclass, and batch-upserts into the `planning_area_risk` RDS table (keyed on `planning_area` + `week`).

## Data Ingestion

Two Lambda functions run every Sunday (16:00 UTC / 00:00 SGT Monday) via EventBridge and write cleaned JSON to `dengue-ml-data-lake`:

- `WeatherDataIngestFunction` — fetches the previous day's **rainfall** and **air temperature** readings from the NEA real-time API
- `DengueDataIngestFunction` — fetches active **dengue cluster** locations and case sizes from the NEA datasets API

All data lands under `raw/weather/` and `raw/dengue/`, partitioned by date.

## Notification System

The notification service is an SQS-buffered, event-driven pipeline:

1. **Amazon S3** receives `predictions.json` from SageMaker.
2. **Dispatcher Lambda** (S3 → SQS): identifies subscribers whose monitored planning areas have worsened risk, and pushes them to SQS in batches of 10. EventBridge also fires the detector 30 minutes after the SageMaker job (Monday 06:30 SGT).
3. **Amazon SQS** buffers email requests with a dead-letter queue (3 retries, 14-day retention).
4. **Worker Lambda** (SQS → SES): consumes batches of 10, renders HTML email alerts, and dispatches via Amazon SES with partial-batch-failure reporting to prevent duplicate sends.
5. **Amazon SES** delivers the final email to verified subscribers.

SES identity verification is triggered automatically when a new email address subscribes for the first time (skipped if already verified or pending).
