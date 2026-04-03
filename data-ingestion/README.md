# Data Ingestion

Ingests real-time weather and dengue cluster data from [data.gov.sg](https://data.gov.sg) into S3, scheduled weekly via Amazon EventBridge.

## Overview

Two Lambda functions run every Sunday and write cleaned JSON to `dengue-ml-data-lake`:

```
dengue-ml-data-lake/
└── raw/
    ├── weather/date=YYYY-MM-DD/rainfall.json
    ├── weather/date=YYYY-MM-DD/air-temperature.json
    └── dengue/date=YYYY-MM-DD/clusters.json
```

| Function | Source | Output |
|---|---|---|
| `WeatherDataIngestFunction` | data.gov.sg real-time API | Rainfall + air temperature for the previous day |
| `DengueDataIngestFunction` | data.gov.sg datasets API | Current dengue cluster locations and case sizes |

---

## Repo Structure

```
data-ingestion/
├── lambdas/
│   ├── weather/
│   │   └── lambda_function.py
│   └── dengue/
│       └── lambda_function.py
├── iam/
│   └── LambdaDataIngestionPolicy.json
└── README.md
```

---

## Setup

### 1. S3 Bucket

1. Go to **S3** in the AWS Console
2. Click **Create bucket**
3. Name it `dengue-ml-data-lake`
4. Leave all other settings as default and click **Create bucket**

### 2. IAM Policy

1. Go to **IAM → Policies → Create policy**
2. Switch to the **JSON** editor
3. Paste the contents of `iam/LambdaDataIngestionPolicy.json`
4. Name it `LambdaDataIngestionPolicy` and click **Create policy**

This grants the Lambda functions write access to the `raw/` prefix in the bucket.

### 3. Lambda Functions

Repeat the following steps for both functions.

**Create the function**

1. Go to **Lambda → Create function**
2. Select **Author from scratch**
3. Set the function name (`WeatherDataIngestFunction` or `DengueDataIngestFunction`)
4. Set runtime to **Python 3.12**
5. Click **Create function**

**Add the code**

1. In the **Code** tab, paste the contents of the relevant `lambda_function.py` into the inline editor
2. Click **Deploy**

**Attach the IAM policy**

1. Go to **Configuration → Permissions**
2. Click the execution role link — this opens IAM in a new tab
3. Click **Add permissions → Attach policies**
4. Search for `LambdaDataIngestionPolicy` and attach it

**Add environment variable** *(WeatherDataIngestFunction only)*

1. Go to **Configuration → Environment variables → Edit**
2. Add a new variable:

| Key | Value |
|---|---|
| `API_KEY` | Your data.gov.sg API key |

**Add the EventBridge trigger** *(both functions)*

1. Go to **Configuration → Triggers → Add trigger**
2. Select **EventBridge (CloudWatch Events)**
3. Select **Create a new rule** and name it `DataIngestionSchedule`
4. Set rule type to **Schedule expression**
5. Enter the cron expression: `cron(0 16 ? * Sun *)`

This runs every Sunday at 16:00 UTC (00:00 SGT Monday).

> If `DataIngestionSchedule` already exists, select **Use existing rule** instead of creating a new one.

---

## Testing

1. Open the function in the Lambda console
2. Go to the **Test** tab and create a new test event with an empty payload: `{}`
3. Click **Test**
4. Check `dengue-ml-data-lake` in S3 — files should appear under `raw/weather/date=<yesterday>/` or `raw/dengue/date=<today>/`

A successful run returns:

```json
{ "statusCode": 200, "body": "Weather ingestion completed" }
{ "statusCode": 200, "body": "Dengue ingestion completed" }
```

---

## Notes

- All timestamps use **Singapore Time (SGT)** via `ZoneInfo("Asia/Singapore")`
- The weather function fetches data for **yesterday's date** — the API returns full-day readings only after the day has ended
- The dengue function first polls for a signed download URL, then fetches the dataset — both steps must succeed for data to be written
- No external dependencies are required; both functions use only `boto3` and `urllib` which are built into the Lambda Python runtime