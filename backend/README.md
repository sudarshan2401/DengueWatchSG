# Backend

The backend is built with Python and deployed as AWS Lambda functions behind an API Gateway. It interacts with Amazon RDS (PostgreSQL) for data storage.

## API Endpoints

| Method | Path                  | Description                                                                   |
| ------ | --------------------- | ----------------------------------------------------------------------------- |
| `GET`  | `/risk`               | Current weekly risk scores for all planning areas (served via CloudFront CDN) |
| `GET`  | `/postal-code/{code}` | Resolve a Singapore postal code to a planning area and coordinates via OneMap |
| `GET`  | `/planning-areas`     | GeoJSON FeatureCollection of Singapore planning area boundaries from OneMap   |
| `POST` | `/subscribe`          | Create or update an email subscription with planning areas to monitor         |
| `GET`  | `/subscribe`          | List all subscriptions (admin use only)                                       |

The `/risk` endpoint is fronted by a separate CloudFront distribution with a 2-day cache TTL (`Cache-Control: max-age=172800`). All other endpoints go through the API Gateway directly.

## Risk Map Ingestion

An S3-triggered Lambda (`backend/risk_map/ingestion/`) listens for new `predictions.json` objects via SNS. It validates the JSON schema, parses each record into a `PredictionRecord` dataclass, and batch-upserts into the `planning_area_risk` RDS table (keyed on `planning_area` + `week`).

## Local Development

```bash
cd backend
pip install -r requirements.txt
python local_server.py
```
