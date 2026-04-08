# DengueWatch SG

A dengue risk prediction web platform for Singapore, providing real-time risk maps, postal code monitoring, and email notifications when risk levels change.

## Architecture Overview

| Layer          | Technology                                                             |
| -------------- | ---------------------------------------------------------------------- |
| Frontend       | React (TypeScript) + Vite, hosted on AWS S3 + CloudFront               |
| Backend        | Python, AWS API Gateway + Lambda                                       |
| Database       | Amazon RDS (PostgreSQL)                                                |
| ML Pipeline    | Python, Amazon SageMaker (XGBoost weekly batch inference)              |
| Data Ingestion | AWS Lambda (Python ETL) pulling from data.gov.sg API                   |
| Risk Ingestion | AWS Lambda triggered by S3 — upserts ML predictions into RDS           |
| Notifications  | S3 → SNS → Dispatcher Lambda → SQS → Worker Lambda → Amazon SES        |
| OneMap         | AWS Lambda auto-refreshes JWT token into SSM Parameter Store every day |
| IaC            | AWS CDK (Python)                                                       |
| Local Dev      | Docker + docker-compose                                                |

## Monorepo Structure

```
cs5224/
├── frontend/          # React + TypeScript + Vite web application
├── backend/           # AWS Lambda functions (REST API)
│   ├── risk_map/      # GET /risk — returns current weekly risk scores
│   │   └── ingestion/ # S3-triggered Lambda that upserts ML predictions into RDS
│   ├── postal_code/   # GET /postal-code/{code} — resolves postal code via OneMap
│   ├── planning_areas/# GET /planning-areas — returns GeoJSON boundaries from OneMap
│   ├── subscriptions/ # POST/GET /subscribe, GET /unsubscribe — manage email subscriptions
│   └── db/            # init.sql database schema
├── notification/      # Standalone notification service (Dispatcher + Worker Lambdas)
│   ├── dispatcher/    # S3 → SQS: identifies affected subscribers, batches into SQS
│   └── worker/        # SQS → SES: sends HTML alert emails via Amazon SES
├── ml/                # SageMaker training & inference scripts
├── data-ingestion/    # ETL Lambdas pulling from data.gov.sg
│   ├── lambdas/       # One folder per Lambda function
│   │   ├── dengue/    # Lambda code for pulling dengue clusters
│   │   └── weather/   # Lambda code for pulling rainfall and air temperature
│   └── iam/           # IAM policy for S3 write access
├── utils/             # Common utilities and standalone services
│   └── onemap_refresher/ # Refreshes OneMap token in SSM
└── README.md
```

## Key Features

- **Risk Map** — weekly dengue risk scores visualised on an interactive map
- **Postal Code Monitoring** — look up risk level for a specific postal code
- **Email Subscriptions** — subscribe to alerts when risk levels change in monitored areas
- **Unsubscribe Page** — one-click unsubscribe via a link in alert emails; accessible at `/unsubscribe?uuid=<subscription-id>`, handles success and error states gracefully

## Getting Started

### Prerequisites

- Node.js 18+
- Python 3.11+
- Docker & Docker Compose
- AWS CLI configured

### Local Development

```bash
# Frontend only (http://localhost:5173)
cd frontend && npm install && npm run dev

# Backend only (http://localhost:8000)
cd backend && pip install -r requirements.txt && python local_server.py
```

### Deploying the Notification Service

```bash
cd notification
./deploy.sh
```

## Component Details

For detailed information about each component, refer to their respective READMEs:

- [Frontend](frontend/README.md)
- [Backend](backend/README.md)
- [Data Ingestion](data-ingestion/README.md)
- [Machine Learning Pipeline](ml/README.md)
- [Notification Service](notification/README.md)
- [Utilities](utils/README.md)
