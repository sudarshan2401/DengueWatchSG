# DengueWatch SG

A dengue risk prediction web platform for Singapore, providing real-time risk maps, postal code monitoring, and email notifications when risk levels change.

## Architecture Overview

| Layer | Technology |
|---|---|
| Frontend | React (TypeScript) + Vite, hosted on AWS S3 + CloudFront |
| Backend | Python, AWS API Gateway + Lambda |
| Database | Amazon RDS (PostgreSQL) |
| ML Pipeline | Python, Amazon SageMaker (XGBoost weekly batch inference) |
| Data Ingestion | AWS Lambda (Python ETL) pulling from NEA data.gov.sg API |
| Notifications | AWS Lambda → SQS → SNS email delivery |
| IaC | AWS CDK (Python) |
| Local Dev | Docker + docker-compose |

## Monorepo Structure

```
cs5224/
├── frontend/          # React + TypeScript + Vite web application
├── backend/           # AWS Lambda functions (REST API)
├── ml/                # SageMaker training & inference scripts
├── infra/             # AWS CDK infrastructure-as-code
├── data-ingestion/    # ETL Lambda pulling from NEA data.gov.sg
├── docker-compose.yml # Local development environment
├── .gitignore
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

## Frontend Pages

1. **Landing Page** (`/`) — Interactive choropleth map of Singapore planning areas colour-coded by predicted dengue risk (Low / Medium / High), postal code search bar, and notification bell icon.
2. **Notification Subscription Page** (`/subscribe`) — Users enter their email address and add postal codes to monitor for risk changes.

## ML Pipeline

- **Scheduler**: Amazon EventBridge triggers weekly SageMaker batch inference job every Monday.
- **Features**: lagged dengue case counts (1–4 weeks), lagged rainfall/temperature (2–3 weeks), week-of-year.
- **Model**: XGBoost multi-class classifier (Low / Medium / High).

## Data Ingestion

- Daily EventBridge schedule triggers an ETL Lambda that fetches dengue cluster and weather data from the NEA data.gov.sg API and upserts into RDS.

## Notification System

1. Post-inference Lambda compares new risk scores with previous week.
2. Areas with worsened risk (e.g. Low → Medium) are pushed to SQS.
3. SNS delivers email notifications to subscribed users.