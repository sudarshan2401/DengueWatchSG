# Utilities

This folder contains supporting microservices and utilities separated from main dengue API backend:

1. **`onemap_refresher`**: A scheduled AWS Lambda function (via EventBridge) that runs daily to refresh the OneMap API JWT token. It retrieves credentials from AWS Systems Manager (SSM) Parameter Store, fetches a new token, and saves it back to SSM so other services can use it.
