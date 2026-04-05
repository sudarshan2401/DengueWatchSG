# Frontend

The frontend is a React (TypeScript) + Vite web application, hosted on AWS S3 + CloudFront.

## Pages

1. **Landing Page** (`/`) — Interactive choropleth map of Singapore planning areas colour-coded by predicted dengue risk (Low / Medium / High), postal code search bar, and notification bell icon.
2. **Notification Subscription Page** (`/subscribe`) — Users enter their email address and add postal codes to monitor for risk changes.

## Local Development

```bash
cd frontend
npm install
npm run dev
```
